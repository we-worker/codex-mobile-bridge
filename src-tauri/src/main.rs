#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
mod worker;

use base64::{engine::general_purpose::STANDARD, Engine};
use serde_json::{json, Value};
use std::{
    path::PathBuf,
    sync::atomic::{AtomicBool, Ordering},
};
use tauri::{
    menu::{Menu, MenuItem},
    tray::{TrayIconBuilder, TrayIconEvent},
    Manager, WebviewUrl, WebviewWindow, WebviewWindowBuilder,
};
use tauri_plugin_autostart::ManagerExt;
use tauri_plugin_clipboard_manager::ClipboardExt;
use tauri_plugin_dialog::{DialogExt, MessageDialogButtons, MessageDialogKind};
use tauri_plugin_opener::OpenerExt;
use worker::Gateway;

struct DesktopState {
    gateway: Gateway,
    quitting: AtomicBool,
    operations: tokio::sync::Mutex<()>,
}

fn local_page(url: &tauri::Url) -> bool {
    (url.scheme() == "tauri" && url.host_str() == Some("localhost")
        || url.scheme() == "http" && url.host_str() == Some("tauri.localhost"))
        && url.path() == "/desktop/index.html"
        && url.username().is_empty()
        && url.password().is_none()
        && url.port().is_none()
}

fn text(value: &Value) -> Result<&str, String> {
    value.as_str().ok_or("操作参数格式错误".into())
}

fn startup(app: &tauri::AppHandle) -> Value {
    json!({"supported":!cfg!(debug_assertions),"enabled":app.autolaunch().is_enabled().unwrap_or(false)})
}

fn decorate(app: &tauri::AppHandle, mut value: Value) -> Value {
    let mut rows = Vec::new();
    if let Ok(interfaces) = if_addrs::get_if_addrs() {
        for interface in interfaces {
            if let std::net::IpAddr::V4(address) = interface.ip() {
                let octets = address.octets();
                let is_tailnet = octets[0] == 100 && (64..=127).contains(&octets[1]);
                if !address.is_loopback()
                    && !is_tailnet
                    && !rows
                        .iter()
                        .any(|r: &Value| r["address"] == address.to_string())
                {
                    rows.push(json!({"name":interface.name,"address":address.to_string()}));
                }
            }
        }
    }
    value["networkInterfaces"] = json!(rows);
    value["loginStartup"] = startup(app);
    value
}

async fn file_dialog(app: tauri::AppHandle, kind: String) -> Result<Option<PathBuf>, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let picker = app.dialog().file();
        let picked = match kind.as_str() {
            "folder" | "data" => picker.blocking_pick_folder(),
            "file" | "ssh-key" => picker.blocking_pick_file(),
            "export" => picker
                .set_file_name("Codex-deployment.zip")
                .add_filter("ZIP", &["zip"])
                .blocking_save_file(),
            _ => return Err("未知路径类型".into()),
        };
        picked
            .map(|p| p.into_path().map_err(|_| "请选择本机文件路径".to_string()))
            .transpose()
    })
    .await
    .map_err(|e| e.to_string())?
}

fn clipboard(app: &tauri::AppHandle, content: String) -> Result<(), String> {
    app.clipboard()
        .write_text(content)
        .map_err(|e| e.to_string())
}

async fn dispatch(app: &tauri::AppHandle, action: &str, payload: Value) -> Result<Value, String> {
    let state = app.state::<DesktopState>();
    let gateway = &state.gateway;
    match action {
        "install-update" => Err("此版本请从项目下载页面手动更新。".into()),
        "choose" => {
            let kind = text(&payload)?.to_string();
            let Some(path) = file_dialog(app.clone(), kind.clone()).await? else {
                return Ok(Value::Null);
            };
            let selected = json!(path.to_string_lossy());
            if kind == "data" {
                gateway.call("set-data-dir", selected).await
            } else {
                Ok(selected)
            }
        }
        "open" => {
            let target = gateway.call("open", payload).await?;
            let value = text(&target["value"])?;
            if target["kind"] == "path" {
                app.opener()
                    .open_path(value, None::<&str>)
                    .map_err(|e| e.to_string())?;
            } else {
                app.opener()
                    .open_url(value, None::<&str>)
                    .map_err(|e| e.to_string())?;
            }
            Ok(Value::Null)
        }
        "copy" => {
            clipboard(
                app,
                text(&gateway.call("copy", payload).await?)?.to_string(),
            )?;
            Ok(Value::Null)
        }
        "tailscale-authorize" => {
            let url = gateway.call(action, payload).await?;
            app.opener()
                .open_url(text(&url)?, None::<&str>)
                .map_err(|e| e.to_string())?;
            Ok(json!({"message":"已打开 Tailscale 授权页面。"}))
        }
        "server-setup" => {
            if !matches!(
                payload["action"].as_str(),
                Some("host" | "trust" | "inspect")
            ) {
                return Err("App 仅支持 SSH 连接检查。".into());
            }
            if payload["action"] == "trust" {
                let current = gateway
                    .call("server-setup", json!({"id":payload["id"],"action":"host"}))
                    .await?;
                if current["fingerprint"] != payload["fingerprint"] {
                    return Err("主机指纹已变化，请重新检查。".into());
                }
                let dialog_app = app.clone();
                let detail = format!(
                    "{}:{}\n{}\n请与服务器管理员或控制台中的指纹核对。",
                    current["host"].as_str().unwrap_or(""),
                    current["port"],
                    text(&current["fingerprint"])?
                );
                let confirmed = tauri::async_runtime::spawn_blocking(move || {
                    dialog_app
                        .dialog()
                        .message(detail)
                        .title("信任此服务器？")
                        .kind(MessageDialogKind::Warning)
                        .buttons(MessageDialogButtons::OkCancelCustom(
                            "信任此服务器".into(),
                            "取消".into(),
                        ))
                        .blocking_show()
                })
                .await
                .map_err(|e| e.to_string())?;
                if !confirmed {
                    return Ok(json!({"cancelled":true,"message":"未保存主机指纹。"}));
                }
            }
            gateway.call(action, payload).await
        }
        "copy-server-diagnostics" => {
            let result = gateway.call("server-setup", json!({"id":payload["id"],"action":"diagnostics","language":payload["language"]})).await?;
            clipboard(app, text(&result["prompt"])?.to_string())?;
            Ok(json!({"message":"服务器只读检查 Prompt 已复制。"}))
        }
        "export-deployment" => {
            let Some(path) = file_dialog(app.clone(), "export".into()).await? else {
                return Ok(Value::Null);
            };
            let result = gateway.call(action, payload).await?;
            std::fs::copy(text(&result["path"])?, &path).map_err(|e| e.to_string())?;
            Ok(json!({"message":format!("部署包已导出：{}",path.display())}))
        }
        "copy-deployment" => {
            let result = gateway.call("deployment", payload.clone()).await?;
            let english = payload["language"] == "en";
            let intro = if english {
                "Manual deployment reference. Review existing services before making changes."
            } else {
                "手动部署参考，请先检查已有服务；管理员操作请由用户自行完成。"
            };
            let mut content = intro.to_string();
            if let Some(files) = result["files"].as_object() {
                for (name, body) in files {
                    if name
                        == if english {
                            "部署说明.md"
                        } else {
                            "DEPLOYMENT_EN.md"
                        }
                    {
                        continue;
                    }
                    content.push_str(&format!("\n\n--- {name} ---\n{}", text(body)?));
                }
            }
            clipboard(app, content)?;
            Ok(json!({"message":"部署说明与配置已复制。"}))
        }
        "pairing" => {
            let mut grant = gateway.call(action, payload.clone()).await?;
            if payload["action"] == "create" {
                let image = qrcode::QrCode::new(text(&grant["url"])?.as_bytes()).map(|code| {
                    code.render::<qrcode::render::svg::Color>()
                        .min_dimensions(320, 320)
                        .build()
                });
                match image {
                    Ok(svg) => {
                        grant
                            .as_object_mut()
                            .ok_or("配对响应格式错误")?
                            .remove("url");
                        grant["image"] = json!(format!(
                            "data:image/svg+xml;base64,{}",
                            STANDARD.encode(svg)
                        ));
                    }
                    Err(_) => {
                        let _ = gateway
                            .call("pairing", json!({"action":"revoke","id":grant["id"]}))
                            .await;
                        return Err("无法生成本地二维码".into());
                    }
                }
            }
            Ok(grant)
        }
        "accounts" if payload["action"] == "openLogin" => {
            let value = gateway.call(action, payload).await?;
            app.opener()
                .open_url(text(&value["url"])?, None::<&str>)
                .map_err(|e| e.to_string())?;
            Ok(value["result"].clone())
        }
        "desktop-sessions" if payload["action"] == "copy-claude-workspace" => {
            let value = gateway.call(action, json!({"action":"status"})).await?;
            clipboard(app, text(&value["claudeWorkspace"])?.to_string())?;
            Ok(json!({"copied":true}))
        }
        "desktop-sessions" if payload["action"] == "prepare-claude" => {
            let mut value = gateway.call(action, payload).await?;
            clipboard(app, text(&value["script"])?.to_string())?;
            value.as_object_mut().unwrap().remove("script");
            Ok(value)
        }
        "save" => {
            let mut value = payload;
            let autostart = value.get("loginStartup").cloned();
            if let Some(enabled) = &autostart {
                if !enabled.is_boolean() || cfg!(debug_assertions) {
                    return Err("请使用已安装的应用设置登录自启。".into());
                }
                if enabled == true {
                    value["preferences"]["autoStart"] = json!(true);
                }
            }
            let result = gateway.call(action, value).await?;
            if result.get("validationError").is_some() {
                return Ok(result);
            }
            if let Some(enabled) = autostart {
                if enabled == true {
                    app.autolaunch().enable()
                } else {
                    app.autolaunch().disable()
                }
                .map_err(|e| e.to_string())?;
            }
            Ok(decorate(app, result))
        }
        "snapshot" => Ok(decorate(app, gateway.call(action, payload).await?)),
        "set-language" => {
            let result = gateway.call(action, payload).await?;
            if let Some(window) = app.get_webview_window("main") {
                window
                    .set_title(if result == "en" {
                        "Codex Mobile Bridge"
                    } else {
                        "Codex 手机网关"
                    })
                    .map_err(|e| e.to_string())?;
            }
            Ok(result)
        }
        "language"
        | "check-update"
        | "skip-update"
        | "notification-watches"
        | "transfer-settings"
        | "devices"
        | "install-cloudflared"
        | "check-cloudflared"
        | "tailscale-setup"
        | "connection-credentials"
        | "read-credentials"
        | "accounts"
        | "cli-access"
        | "desktop-sessions"
        | "harness"
        | "account"
        | "start"
        | "stop"
        | "logs"
        | "test-notification"
        | "check-entry" => gateway.call(action, payload).await,
        _ => Err("未知操作".into()),
    }
}

#[tauri::command]
async fn bridge(
    app: tauri::AppHandle,
    window: WebviewWindow,
    action: String,
    payload: Value,
) -> Result<Value, String> {
    if window.label() != "main" || !local_page(&window.url().map_err(|e| e.to_string())?) {
        return Err("不允许的界面来源".into());
    }
    let state = app.state::<DesktopState>();
    let _operation = state.operations.lock().await;
    dispatch(&app, &action, payload).await
}

fn show(app: &tauri::AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
}

fn primary_url(snapshot: &Value) -> Option<String> {
    if snapshot["runtime"]["running"] != true {
        return None;
    }
    let urls = snapshot["urls"].as_array()?;
    let valid: Vec<_> = urls
        .iter()
        .filter_map(|v| v.as_str())
        .filter(|s| {
            tauri::Url::parse(s).is_ok_and(|u| {
                matches!(u.scheme(), "http" | "https")
                    && u.username().is_empty()
                    && u.password().is_none()
            })
        })
        .collect();
    valid
        .iter()
        .find(|s| s.starts_with("https:"))
        .or_else(|| {
            valid.iter().find(|s| {
                tauri::Url::parse(s).is_ok_and(|u| {
                    !matches!(u.host_str(), Some("127.0.0.1" | "localhost" | "[::1]"))
                })
            })
        })
        .or_else(|| valid.first())
        .map(|s| s.to_string())
}

fn tray_action(app: &tauri::AppHandle, action: &str) {
    let app = app.clone();
    let action = action.to_string();
    tauri::async_runtime::spawn(async move {
        let state = app.state::<DesktopState>();
        let _operation = state.operations.lock().await;
        let result = async {
            if action == "stop" {
                state.gateway.call("stop", Value::Null).await?;
                state.quitting.store(true, Ordering::SeqCst);
                app.exit(0);
                return Ok::<(), String>(());
            }
            let snapshot = state.gateway.call("snapshot", Value::Null).await?;
            let url = primary_url(&snapshot).ok_or("网关未启动或没有可用地址")?;
            // Revalidate against fresh allowed URLs through the same host path.
            dispatch(
                &app,
                if action == "phone" { "open" } else { "copy" },
                json!(url),
            )
            .await?;
            Ok(())
        }
        .await;
        if let Err(error) = result {
            show(&app);
            app.dialog()
                .message(error)
                .title("网关操作未完成")
                .show(|_| {});
        }
    });
}

fn main() {
    let mut builder = tauri::Builder::default();
    // The native smoke runner needs its isolated fixture to coexist with an
    // already-running installed control panel. Production launches do not set
    // CMB_TAURI_DEBUG_PORT and always keep the single-instance guard first.
    if std::env::var_os("CMB_TAURI_DEBUG_PORT").is_none() {
        builder = builder.plugin(tauri_plugin_single_instance::init(|app, args, _| {
            if !args.iter().any(|a| a == "--login-startup") {
                show(app);
            }
        }));
    }
    builder
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_clipboard_manager::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(
            tauri_plugin_autostart::Builder::new()
                .args(["--login-startup"])
                .build(),
        )
        .plugin(
            tauri::plugin::Builder::<tauri::Wry>::new("local-navigation")
                .on_navigation(|_, url| local_page(url))
                .build(),
        )
        .invoke_handler(tauri::generate_handler![bridge])
        .setup(|app| {
            let desktop = if let Some(directory) = std::env::var_os("CMB_DATA_DIR") {
                PathBuf::from(directory).join("desktop-runtime-tauri")
            } else {
                dirs::config_dir()
                    .ok_or("无法定位用户配置目录")?
                    .join("Codex Mobile Bridge")
            };
            let location = desktop.join("bridge-location.json");
            let selected = std::fs::read(location)
                .ok()
                .and_then(|b| serde_json::from_slice::<Value>(&b).ok())
                .and_then(|v| v["dataDir"].as_str().map(PathBuf::from));
            let data = std::env::var_os("CMB_DATA_DIR")
                .map(PathBuf::from)
                .or(selected)
                .unwrap_or_else(|| desktop.join("gateway"));
            let resource = app.path().resource_dir()?;
            let executable = resource.join("gateway").join(if cfg!(windows) {
                "codex-mobile-gateway.exe"
            } else {
                "codex-mobile-gateway"
            });
            let (executable, prefix) =
                if cfg!(debug_assertions) && std::env::var_os("CMB_TAURI_SOURCE").is_some() {
                    (
                        PathBuf::from(std::env::var("CMB_PYTHON").unwrap_or("python".into())),
                        vec![
                            "-B".into(),
                            PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                                .parent()
                                .unwrap()
                                .join("desktop.py")
                                .to_string_lossy()
                                .into_owned(),
                        ],
                    )
                } else {
                    (executable, vec![])
                };
            app.manage(DesktopState {
                gateway: Gateway::new(executable, prefix, data, desktop),
                quitting: AtomicBool::new(false),
                operations: tokio::sync::Mutex::new(()),
            });
            let open = MenuItem::with_id(app, "show", "打开控制面板", true, None::<&str>)?;
            let status = MenuItem::with_id(app, "status", "正在读取状态", false, None::<&str>)?;
            let phone = MenuItem::with_id(app, "phone", "打开手机访问地址", false, None::<&str>)?;
            let copy = MenuItem::with_id(app, "copy-url", "复制手机访问地址", false, None::<&str>)?;
            let leave =
                MenuItem::with_id(app, "leave", "退出控制面板（保留网关）", true, None::<&str>)?;
            let stop = MenuItem::with_id(app, "stop", "停止网关并退出", false, None::<&str>)?;
            let menu = Menu::with_items(app, &[&open, &status, &phone, &copy, &stop, &leave])?;
            TrayIconBuilder::with_id("gateway")
                .icon(app.default_window_icon().ok_or("缺少应用图标")?.clone())
                .tooltip("Codex 手机网关")
                .menu(&menu)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "show" => show(app),
                    "leave" => {
                        app.state::<DesktopState>()
                            .quitting
                            .store(true, Ordering::SeqCst);
                        app.exit(0);
                    }
                    "stop" | "phone" | "copy-url" => tray_action(app, event.id.as_ref()),
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if matches!(event, TrayIconEvent::DoubleClick { .. }) {
                        show(tray.app_handle());
                    }
                })
                .build(app)?;
            let tray_app = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                loop {
                    {
                        let state = tray_app.state::<DesktopState>();
                        if state.quitting.load(Ordering::SeqCst) {
                            break;
                        }
                        if let Ok(_operation) = state.operations.try_lock() {
                            if let Ok(snapshot) = state.gateway.call("snapshot", Value::Null).await
                            {
                                let running = snapshot["runtime"]["running"] == true;
                                let english = snapshot["desktopLanguage"] == "en";
                                let label = |zh: &str, en: &str| {
                                    if english {
                                        en.to_string()
                                    } else {
                                        zh.to_string()
                                    }
                                };
                                let _ = status.set_text(if running {
                                    label("网关运行中", "Gateway running")
                                } else {
                                    label("网关未启动", "Gateway stopped")
                                });
                                let _ = open.set_text(label("打开控制面板", "Open control panel"));
                                let _ = phone.set_text(label("打开手机访问地址", "Open phone URL"));
                                let _ = copy.set_text(label("复制手机访问地址", "Copy phone URL"));
                                let _ =
                                    stop.set_text(label("停止网关并退出", "Stop gateway and quit"));
                                let _ = leave.set_text(label(
                                    "退出控制面板（保留网关）",
                                    "Quit control panel (keep gateway running)",
                                ));
                                let available = primary_url(&snapshot).is_some();
                                let _ = phone.set_enabled(available);
                                let _ = copy.set_enabled(available);
                                let _ = stop.set_enabled(running);
                            }
                        };
                    }
                    tokio::time::sleep(std::time::Duration::from_secs(5)).await;
                }
            });
            let hidden = std::env::args().any(|a| a == "--login-startup");
            let mut builder = WebviewWindowBuilder::new(
                app,
                "main",
                WebviewUrl::App("desktop/index.html".into()),
            )
            .title("Codex 手机网关")
            .inner_size(1100.0, 850.0)
            .min_inner_size(820.0, 640.0)
            .visible(!hidden)
            .initialization_script(include_str!("../../desktop/tauri-bridge.js"));
            if let Some(directory) = std::env::var_os("CMB_DATA_DIR") {
                builder = builder.data_directory(PathBuf::from(directory).join("tauri-webview"));
            }
            if let Ok(debug_port) = std::env::var("CMB_TAURI_DEBUG_PORT") {
                let debug_port = debug_port.trim();
                if debug_port.parse::<u16>().is_ok() {
                    builder = builder.additional_browser_args(&format!(
                        "--disable-features=msWebOOUI,msPdfOOUI,msSmartScreenProtection \
                         --remote-debugging-address=127.0.0.1 \
                         --remote-debugging-port={debug_port}"
                    ));
                }
            }
            builder.build()?;
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                if !window
                    .state::<DesktopState>()
                    .quitting
                    .load(Ordering::SeqCst)
                {
                    api.prevent_close();
                    let _ = window.hide();
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("无法启动 Tauri 客户端");
}
