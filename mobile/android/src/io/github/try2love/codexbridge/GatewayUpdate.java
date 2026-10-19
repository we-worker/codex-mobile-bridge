package io.github.try2love.codexbridge;

import java.io.*;
import java.net.*;
import org.json.*;

/** One explicitly selected gateway. No redirects, arbitrary destinations or stored credentials. */
final class GatewayUpdate {
 interface Progress {void changed(long downloaded,long size);}
 final String base;private final String cookie;private final ArtifactDownload.Cookies cookies;
 private volatile boolean cancelled;private volatile HttpURLConnection active;
 GatewayUpdate(String base,ArtifactDownload.Cookies cookies)throws IOException {
  try{if(!GatewayURL.origin(base).equals(base))throw new IOException();}catch(Exception e){throw new IOException("请先连接并登录电脑网关",e);}
  this.base=base;this.cookies=cookies;cookie=cookies.read();if(cookie==null||cookie.isEmpty())throw new IOException("请先连接并登录电脑网关");
 }
 void cancel(){cancelled=true;HttpURLConnection c=active;if(c!=null)c.disconnect();}
 private void stopped()throws IOException {if(cancelled||Thread.currentThread().isInterrupted())throw new InterruptedIOException();if(!cookie.equals(cookies.read()))throw new IOException("登录已变化，请重新连接电脑后检查更新");}
 private JSONObject request(String path,JSONObject body)throws IOException {
   stopped();HttpURLConnection connection=TailnetHttp.open(new URL(base+path));active=connection;
  try{
   connection.setConnectTimeout(15000);connection.setReadTimeout(20000);connection.setInstanceFollowRedirects(false);connection.setRequestProperty("Cookie",cookie);connection.setRequestProperty("Origin",GatewayURL.httpOrigin(base));connection.setRequestProperty("Accept","application/json");
   if(body!=null){
    // Fetch the current CSRF token on the same authenticated gateway before a write.
    JSONObject auth=request("/api/auth",null);active=connection;stopped();
    if(!auth.optBoolean("authenticated")||auth.optString("csrf").isEmpty())throw new IOException("请先连接并登录电脑网关");
    byte[] data=body.toString().getBytes("UTF-8");connection.setRequestMethod("POST");connection.setRequestProperty("Content-Type","application/json");connection.setRequestProperty("X-CSRF-Token",auth.optString("csrf"));connection.setDoOutput(true);connection.setFixedLengthStreamingMode(data.length);try(OutputStream out=connection.getOutputStream()){out.write(data);}
   }
   int status=connection.getResponseCode();stopped();
   if(status==404||status==405)throw new IOException("此网关暂不支持协助更新，请先更新电脑网关");
   if(status==401||status==403)throw new IOException("电脑登录已失效，请重新连接电脑后检查更新");
   if(status>=300&&status<400)throw new IOException("电脑更新地址发生跳转，请重新连接电脑");
   InputStream stream=status==200?connection.getInputStream():connection.getErrorStream();
   try(InputStream in=stream;ByteArrayOutputStream bytes=new ByteArrayOutputStream()){
    if(in==null)throw new IOException("电脑协助更新失败，请重试");byte[] block=new byte[8192];int count;
    while((count=in.read(block))!=-1){stopped();if(bytes.size()+count>262144)throw new IOException("电脑更新响应过大");bytes.write(block,0,count);}
    JSONObject result=new JSONObject(bytes.toString("UTF-8"));if(status!=200){String error=result.optString("error");throw new IOException(error.isEmpty()||error.length()>300?"电脑协助更新失败，请重试":error);}return result;
   }
  }catch(JSONException e){throw new IOException("电脑更新响应无效",e);}finally{connection.disconnect();if(active==connection)active=null;}
 }
 MobileRelease check(String current)throws IOException {
  JSONObject value=request("/api/mobile/update?current="+URLEncoder.encode(current,"UTF-8"),null);
  if(!value.optBoolean("supported")||!value.has("release"))throw new IOException("此网关暂不支持协助更新，请先更新电脑网关");
  if(value.isNull("release"))return null;
  try{
   JSONObject row=value.getJSONObject("release");MobileRelease release=new MobileRelease(row.getString("version"),row.optString("notes"),row.getLong("size"),row.getString("sha256"));
   if(!MobileRelease.eligible(current,"v"+release.version,false,row.optBoolean("prerelease",true),MobileRelease.asset(release.version),release.download)||release.size<=0||release.size>MobileRelease.MAX_SIZE||release.sha256==null)throw new IOException("电脑返回的更新信息无效");return release;
  }catch(JSONException|RuntimeException e){throw new IOException("电脑返回的更新信息无效",e);}
 }
 String prepare(MobileRelease release,Progress progress)throws IOException {
  try{
   JSONObject body=new JSONObject().put("version",release.version).put("size",release.size).put("sha256",release.sha256);
   JSONObject value=request("/api/mobile/update/prepare",body);String identifier=value.optString("id");
   if(!identifier.matches("[a-f0-9]{64}"))throw new IOException("电脑更新响应无效");
   long deadline=System.nanoTime()+660_000_000_000L;
   while(true){
    stopped();String state=value.optString("state");long size=value.optLong("size",-1),downloaded=value.optLong("downloaded",-1);
    if(!identifier.equals(value.optString("id"))||size!=release.size||downloaded<0||downloaded>size)throw new IOException("电脑更新响应无效");
    progress.changed(downloaded,size);
    if(state.equals("ready")){if(downloaded!=size)throw new IOException("电脑更新响应无效");return identifier;}
    if(state.equals("failed")){String error=value.optString("error");throw new IOException(error.isEmpty()||error.length()>300?"电脑下载失败，请重试":error);}
    if(!state.equals("downloading"))throw new IOException("电脑更新响应无效");
    if(System.nanoTime()>deadline)throw new IOException("电脑下载超时，请稍后重试");
    try{Thread.sleep(1000);}catch(InterruptedException e){Thread.currentThread().interrupt();throw new InterruptedIOException();}
    value=request("/api/mobile/update/status/"+identifier,null);
   }
  }catch(JSONException e){throw new IOException("更新信息无效",e);}
 }
}
