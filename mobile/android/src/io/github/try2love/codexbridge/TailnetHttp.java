package io.github.try2love.codexbridge;

import java.io.IOException;
import java.net.HttpURLConnection;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.Proxy;
import java.net.URL;

/** Applies the embedded Tailscale CONNECT proxy only to HTTPS .ts.net URLs. */
final class TailnetHttp {
 private static volatile Proxy proxy;

 private TailnetHttp(){}

 static synchronized void activate(String address)throws IOException {
  if(address==null)throw new IOException("内置 Tailscale 未提供本地代理");
  int separator=address.lastIndexOf(':');
  if(separator<=0||separator==address.length()-1)throw new IOException("内置 Tailscale 代理地址无效");
  String host=address.substring(0,separator),portText=address.substring(separator+1);
  if(!host.equals("127.0.0.1")&&!host.equals("localhost"))throw new IOException("内置 Tailscale 代理不在本机回环地址");
  int port;
  try{port=Integer.parseInt(portText);}catch(NumberFormatException invalid){throw new IOException("内置 Tailscale 代理端口无效");}
  if(port<1||port>65535)throw new IOException("内置 Tailscale 代理端口无效");
  proxy=new Proxy(Proxy.Type.HTTP,new InetSocketAddress(InetAddress.getByName("127.0.0.1"),port));
 }

 static synchronized void clear(){proxy=null;}

 static HttpURLConnection open(URL target)throws IOException {
  Proxy current=proxy;
  if(current!=null&&GatewayURL.tailnetOrigin(target.toString()))return (HttpURLConnection)target.openConnection(current);
  return (HttpURLConnection)target.openConnection();
 }
}
