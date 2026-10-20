package io.github.try2love.codexbridge;

import android.content.Context;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import androidx.webkit.ProxyConfig;
import androidx.webkit.ProxyController;
import androidx.webkit.WebViewFeature;
import java.io.File;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import mobiletsnet.Mobile;

/** Owns one userspace Tailscale node and the process-wide WebView proxy. */
final class TailnetController {
 interface Listener {
  void status(String value);
  void authRequired(String url);
  void ready(int localPort);
  void failed(String message);
 }

 private final Context context;
 private final Mobile mobile=new Mobile();
 private final Handler main=new Handler(Looper.getMainLooper());
 private final ExecutorService worker=Executors.newSingleThreadExecutor();
 private int generation;
 private String lastAuthURL="";
 private String lastStatus="";
 private String lastDetail="";

 TailnetController(Context context){this.context=context.getApplicationContext();}

 void start(String target,Listener listener){
  String unsupported=unsupportedWebProxy();
  if(unsupported!=null){
   TailnetHttp.clear();
   listener.failed(unsupported);
   return;
  }
  final int ticket=++generation;
  lastAuthURL="";
  lastStatus="";
  lastDetail="";
  TailnetHttp.clear();
  clearWebProxy(null);
  main.post(()->listener.status("正在启动内置 Tailscale…"));
  worker.execute(()->{
   mobile.stop();
   if(ticket!=generation)return;
   try{
    mobile.start(stateDirectory().getAbsolutePath(),hostname(),TailnetCredentialStore.load(context));
    if(ticket!=generation){mobile.stop();return;}
    Log.i("CodexTailnet","started control="+safeLogValue(mobile.controlPlane())+" proxy="+safeLogValue(mobile.proxyAddress()));
    TailnetHttp.activate(mobile.proxyAddress());
    main.post(()->poll(ticket,listener,target,0));
   }catch(Exception error){
    if(ticket==generation)main.post(()->listener.failed(message(error)));
   }
  });
 }

 private void poll(int ticket,Listener listener,String target,int attempts){
  if(ticket!=generation)return;
  String status=mobile.status();
  logStatus(status);
  if("ready".equals(status)){
   waitForGateway(ticket,listener,target,0);
   return;
  }
  if("auth_required".equals(status)){
   String url=mobile.authURL();
   if(url!=null&&!url.isEmpty()&&!url.equals(lastAuthURL)){
    lastAuthURL=url;
    listener.authRequired(url);
   }
   main.postDelayed(()->poll(ticket,listener,target,attempts+1),750);
   return;
  }
  if("failed".equals(status)){
   String code=mobile.errorCode();
   String detail=mobile.errorDetail();
   if("auth_key_invalid".equals(code)){
    TailnetCredentialStore.clear(context);
    detail="保存的 Tailscale Auth Key 无效或已失效，已从本机清除。请重试并使用浏览器授权，或保存新的 tskey-auth- Auth Key。";
   }
   Log.w("CodexTailnet","connection failed code="+safeLogValue(code)+" control="+safeLogValue(mobile.controlPlane())+" detail="+safeLogValue(detail));
   fail(ticket,listener,failureMessage(code,detail));
   return;
  }
  if("stopped".equals(status)){
   fail(ticket,listener,"内置 Tailscale 已停止，请重新连接。");
   return;
  }
  if(attempts>=600){
   fail(ticket,listener,"内置 Tailscale 启动超时，请检查网络后重试。");
   return;
  }
  int wait="auth_required".equals(status)?1000:250;
  main.postDelayed(()->poll(ticket,listener,target,attempts+1),wait);
 }

 private void waitForGateway(int ticket,Listener listener,String target,int attempts){
  if(ticket!=generation)return;
  worker.execute(()->{
   boolean reachable=gatewayReachable(target);
   if(ticket!=generation)return;
   if(!reachable&&attempts<40){
    main.postDelayed(()->waitForGateway(ticket,listener,target,attempts+1),500);
    return;
   }
   if(!reachable){
    fail(ticket,listener,"内置 Tailscale 已连接，但暂时无法访问目标电脑。请确认电脑端网关仍在运行后重试。");
    return;
   }
   main.post(()->{
    if(ticket!=generation)return;
    try{
     int port=localPort(mobile.proxyAddress());
     applyWebProxy(port,()->{
      if(ticket!=generation)return;
      listener.ready(port);
      main.postDelayed(()->{
       if(ticket==generation)Log.i("CodexTailnet","status=ready detail="+safeLogValue(mobile.diagnostic()));
      },1000);
     });
    }catch(Exception error){
     fail(ticket,listener,error.getMessage());
    }
   });
  });
 }

 private static boolean gatewayReachable(String target){
  HttpURLConnection connection=null;
  try{
   URL url=new URL(target.endsWith("/")?target+"api/auth":target+"/api/auth");
   connection=TailnetHttp.open(url);
   connection.setInstanceFollowRedirects(false);
   connection.setUseCaches(false);
   connection.setConnectTimeout(3000);
   connection.setReadTimeout(3000);
   int status=connection.getResponseCode();
   return status>0&&status!=502&&status!=503&&status!=504;
  }catch(Exception unavailable){
   return false;
  }finally{
   if(connection!=null)connection.disconnect();
  }
 }

 void stop(){
  generation++;
  TailnetHttp.clear();
  clearWebProxy(null);
  worker.execute(mobile::stop);
 }

 void dispose(){
  stop();
  worker.shutdown();
 }

 void reset(Runnable completed){
  generation++;
  TailnetHttp.clear();
  clearWebProxy(()->worker.execute(()->{
   mobile.stop();
   TailnetCredentialStore.clear(context);
   deleteTree(stateDirectory());
   main.post(completed);
  }));
 }

 boolean hasAuthKey(){return TailnetCredentialStore.saved(context);}

 void saveAuthKey(String value)throws Exception{TailnetCredentialStore.save(context,value);}

 void clearAuthKey(){TailnetCredentialStore.clear(context);}

 private void fail(int ticket,Listener listener,String message){
  if(ticket!=generation)return;
  generation++;
  TailnetHttp.clear();
  clearWebProxy(null);
  worker.execute(mobile::stop);
  listener.failed(message==null||message.isEmpty()?"内置 Tailscale 连接失败。":message);
 }

 private void applyWebProxy(int port,Runnable completed)throws Exception {
  String unsupported=unsupportedWebProxy();
  if(unsupported!=null)throw new Exception(unsupported);
  ProxyConfig config=new ProxyConfig.Builder()
   .removeImplicitRules()
   .addProxyRule("http://127.0.0.1:"+port,ProxyConfig.MATCH_HTTP)
   .addProxyRule("http://127.0.0.1:"+port,ProxyConfig.MATCH_HTTPS)
   .addBypassRule("*.ts.net")
   .addBypassRule("100.64.0.0/10")
   .setReverseBypassEnabled(true)
   .build();
  ProxyController.getInstance().setProxyOverride(config,main::post,completed);
 }

 private void clearWebProxy(Runnable completed){
  if(unsupportedWebProxy()!=null){if(completed!=null)completed.run();return;}
  ProxyController.getInstance().clearProxyOverride(main::post,()->{
   if(completed!=null)completed.run();
  });
 }

 private static String unsupportedWebProxy(){
  if(Build.VERSION.SDK_INT<29)return "内置 Tailscale 需要 Android 10 或更高版本；当前系统无法给 WebView 设置进程内代理。";
  if(!WebViewFeature.isFeatureSupported(WebViewFeature.PROXY_OVERRIDE))return "当前 Android WebView 不支持进程内代理，请更新 Android System WebView。";
  if(!WebViewFeature.isFeatureSupported(WebViewFeature.PROXY_OVERRIDE_REVERSE_BYPASS))return "当前 Android WebView 不支持限定 Tailnet 地址的进程内代理，请更新 Android System WebView。";
  return null;
 }

 private int localPort(String address)throws Exception {
  if(address==null)throw new Exception("内置 Tailscale 未提供本地代理");
  int separator=address.lastIndexOf(':');
  if(separator<=0)throw new Exception("内置 Tailscale 代理地址无效");
  int port=Integer.parseInt(address.substring(separator+1));
  if(port<1||port>65535)throw new Exception("内置 Tailscale 代理端口无效");
  return port;
 }

 private File stateDirectory(){return new File(context.getFilesDir(),"tailnet/device");}

 private String hostname(){
  android.content.SharedPreferences prefs=context.getSharedPreferences("bridge-tailnet",0);
  String suffix=prefs.getString("hostnameSuffix","");
  if(suffix.matches("[a-f0-9]{10}"))return "codex-bridge-"+suffix;
  suffix=UUID.randomUUID().toString().replace("-","").substring(0,10);
  prefs.edit().putString("hostnameSuffix",suffix).apply();
  return "codex-bridge-"+suffix;
 }

 private static void deleteTree(File file){
  if(file==null||!file.exists())return;
  File canonical;
  try{canonical=file.getCanonicalFile();}catch(Exception invalid){return;}
  File[] children=canonical.listFiles();
  if(children!=null)for(File child:children)deleteTree(child);
  canonical.delete();
 }

 private static String message(Exception error){
  String value=error==null?null:error.getMessage();
  return value==null||value.isEmpty()?"内置 Tailscale 启动失败。":value;
 }

 private void logStatus(String status){
  if(status==null||status.equals(lastStatus))return;
  lastStatus=status;
  String detail=mobile.diagnostic();
  if(detail==null||detail.equals(lastDetail))detail="";
  else lastDetail=detail;
  Log.i("CodexTailnet","status="+safeLogValue(status)+(detail.isEmpty()?"":" detail="+safeLogValue(detail)));
 }

 private static String safeLogValue(String value){
  if(value==null)return "";
  return value.replace('\n',' ').replace('\r',' ');
 }

 private static String failureMessage(String code,String detail){
  if("authentication_failed".equals(code))return "Tailscale 授权未完成，请重新连接并完成登录。";
  if("auth_key_invalid".equals(code))return detail;
  if("network_timeout".equals(code))return "内置 Tailscale 启动超时，请检查控制面网络后重试。";
  if("network_failed".equals(code))return "Tailscale 网络不可用，请检查网络后重试。";
  if("proxy_failed".equals(code))return "内置 Tailscale 本地代理启动失败，请重试。";
  return "内置 Tailscale 连接失败，请稍后重试。";
 }
}
