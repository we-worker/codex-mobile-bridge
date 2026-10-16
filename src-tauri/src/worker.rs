use serde_json::{json, Value};
use std::{
    io::{BufRead, BufReader, Read, Write},
    path::PathBuf,
    process::{Child, ChildStdin, ChildStdout, Command, Stdio},
};
use tokio::sync::{mpsc, oneshot};

type Reply = Result<Value, String>;
struct Request {
    action: String,
    payload: Value,
    reply: oneshot::Sender<Reply>,
}

#[derive(Clone)]
pub struct Gateway {
    sender: mpsc::Sender<Request>,
}

struct Process {
    child: Child,
    input: Option<ChildStdin>,
    output: BufReader<ChildStdout>,
    healthy: bool,
}

impl Process {
    fn start(
        executable: PathBuf,
        prefix: Vec<String>,
        data: PathBuf,
        desktop: PathBuf,
    ) -> Result<Self, String> {
        let mut command = Command::new(executable);
        command
            .args(prefix)
            .arg("tauri-stream")
            .arg("--data-dir")
            .arg(data)
            .arg("--desktop-dir")
            .arg(desktop)
            .env("PYTHONUTF8", "1")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null());
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            command.creation_flags(0x08000000);
        }
        let mut child = command
            .spawn()
            .map_err(|_| "无法启动随附网关，请检查安装文件。".to_string())?;
        let input = child.stdin.take();
        let output = BufReader::new(child.stdout.take().ok_or("网关未提供私有输出通道")?);
        Ok(Self {
            child,
            input,
            output,
            healthy: true,
        })
    }

    fn call(&mut self, action: &str, payload: Value) -> Reply {
        let mut bytes = serde_json::to_vec(&json!({"action":action,"payload":payload}))
            .map_err(|e| e.to_string())?;
        if bytes.len() > 1024 * 1024 {
            return Err("本机请求超出大小限制".into());
        }
        bytes.push(b'\n');
        self.healthy = false;
        let input = self.input.as_mut().ok_or("本机管理已关闭")?;
        // A broken pipe or malformed reply is never retried or sent to a new owner.
        input
            .write_all(&bytes)
            .and_then(|_| input.flush())
            .map_err(|_| "本机操作结果未知，请刷新确认；不会自动重试。".to_string())?;
        let mut line = String::new();
        Read::by_ref(&mut self.output)
            .take(8 * 1024 * 1024 + 1)
            .read_line(&mut line)
            .map_err(|_| "无法读取操作结果；不会自动重试。".to_string())?;
        if line.len() > 8 * 1024 * 1024 || !line.ends_with('\n') {
            return Err("网关私有通道已断开；操作结果未知，请重新打开控制面板确认。".into());
        }
        let response: Value = serde_json::from_str(&line)
            .map_err(|_| "网关响应格式无效；不会自动重试。".to_string())?;
        if !response["ok"].is_boolean() {
            return Err("网关响应格式无效；不会自动重试。".into());
        }
        self.healthy = true;
        if response["ok"] == true {
            return Ok(response["result"].clone());
        }
        if let Some(fields) = response["validation"].as_object() {
            let mut validation = fields.clone();
            validation.insert("message".into(), response["error"].clone());
            return Ok(json!({"validationError":validation}));
        }
        Err(response["error"]
            .as_str()
            .unwrap_or("本机操作失败")
            .to_string())
    }
}

impl Drop for Process {
    fn drop(&mut self) {
        // EOF lets accepted mutations finish and close local services. Do not
        // terminate the gateway or any Codex process when the window exits.
        self.input.take();
        let _ = self.child.try_wait();
    }
}

impl Gateway {
    pub fn new(executable: PathBuf, prefix: Vec<String>, data: PathBuf, desktop: PathBuf) -> Self {
        let (sender, mut receiver) = mpsc::channel::<Request>(32);
        std::thread::spawn(move || {
            let mut process = Process::start(executable, prefix, data, desktop);
            while let Some(request) = receiver.blocking_recv() {
                let result = match &mut process {
                    Ok(worker) => worker.call(&request.action, request.payload),
                    Err(error) => Err(error.clone()),
                };
                // Domain errors preserve the stream. A dead child poisons the
                // owner instead of silently creating another local executor.
                if let Ok(worker) = &mut process {
                    if !worker.healthy || matches!(worker.child.try_wait(), Ok(Some(_))) {
                        process = Err("网关管理通道已关闭，请重新打开控制面板。".into());
                    }
                }
                let _ = request.reply.send(result);
            }
        });
        Self { sender }
    }

    pub async fn call(&self, action: &str, payload: Value) -> Reply {
        self.call_with_timeout(action, payload, std::time::Duration::from_secs(180))
            .await
    }

    async fn call_with_timeout(
        &self,
        action: &str,
        payload: Value,
        timeout: std::time::Duration,
    ) -> Reply {
        let (reply, receive) = oneshot::channel();
        self.sender
            .try_send(Request {
                action: action.to_string(),
                payload,
                reply,
            })
            .map_err(|_| "本机操作队列忙，请稍后重试；本次操作尚未发送。".to_string())?;
        // The worker keeps its place in the queue until the original result is
        // drained. A timeout never closes, replays or overlaps a pending write.
        tokio::time::timeout(timeout, receive)
            .await
            .map_err(|_| "操作仍在处理，结果暂不确定，请刷新确认；不会自动重试。".to_string())?
            .map_err(|_| "本机管理通道已关闭".to_string())?
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fixture() -> (tempfile::TempDir, Gateway) {
        let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .unwrap()
            .join(".tmp");
        std::fs::create_dir_all(&root).unwrap();
        let directory = tempfile::tempdir_in(root).unwrap();
        let script = r#"
import json,sys,time
from pathlib import Path
log=Path(sys.argv[sys.argv.index('--data-dir')+1])/'requests.jsonl'
for line in sys.stdin:
    request=json.loads(line); action=request['action']
    with log.open('a', newline='\n') as stream: stream.write(json.dumps(action)+'\n')
    if action=='slow': time.sleep(.15)
    if action=='broken': print('{broken',flush=True)
    elif action=='domain': print(json.dumps({'ok':False,'error':'fixture rejection'}),flush=True)
    else: print(json.dumps({'ok':True,'result':action}),flush=True)
"#;
        let gateway = Gateway::new(
            PathBuf::from(std::env::var("CMB_TEST_PYTHON").unwrap_or("python".into())),
            vec!["-u".into(), "-c".into(), script.into()],
            directory.path().to_path_buf(),
            directory.path().to_path_buf(),
        );
        (directory, gateway)
    }

    fn runtime() -> tokio::runtime::Runtime {
        tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
            .unwrap()
    }

    #[test]
    fn unknown_write_is_not_replayed_and_late_response_is_drained() {
        let (directory, gateway) = fixture();
        runtime().block_on(async {
            assert!(gateway
                .call_with_timeout("slow", Value::Null, std::time::Duration::from_millis(5))
                .await
                .is_err());
            assert_eq!(
                gateway.call("next", Value::Null).await.unwrap(),
                json!("next")
            );
        });
        assert_eq!(
            std::fs::read_to_string(directory.path().join("requests.jsonl")).unwrap(),
            "\"slow\"\n\"next\"\n"
        );
    }

    #[test]
    fn corrupted_protocol_closes_owner_instead_of_resending() {
        let (directory, gateway) = fixture();
        runtime().block_on(async {
            assert!(gateway.call("broken", Value::Null).await.is_err());
            assert!(gateway.call("must-not-send", Value::Null).await.is_err());
        });
        assert_eq!(
            std::fs::read_to_string(directory.path().join("requests.jsonl")).unwrap(),
            "\"broken\"\n"
        );
    }

    #[test]
    fn domain_error_preserves_same_private_process() {
        let (directory, gateway) = fixture();
        runtime().block_on(async {
            assert_eq!(
                gateway.call("domain", Value::Null).await.unwrap_err(),
                "fixture rejection"
            );
            assert_eq!(
                gateway.call("next", Value::Null).await.unwrap(),
                json!("next")
            );
        });
        assert_eq!(
            std::fs::read_to_string(directory.path().join("requests.jsonl")).unwrap(),
            "\"domain\"\n\"next\"\n"
        );
    }
}
