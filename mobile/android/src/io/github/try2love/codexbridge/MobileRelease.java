package io.github.try2love.codexbridge;

import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Release selection is independent of the gateway and never changes its login. */
public final class MobileRelease {
 public static final String REPO="https://github.com/try2love/codex-mobile-bridge";
 public static final String API="https://api.github.com/repos/try2love/codex-mobile-bridge/releases?per_page=100";
 public static final long MAX_SIZE=512L*1024*1024;
 private static final Pattern VERSION=Pattern.compile("^(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)(?:-(alpha|beta|preview|rc)\\.(0|[1-9][0-9]*))?$");
 public final String version,notes,download;public final long size;public final String sha256;
 public MobileRelease(String version,String notes){this(version,notes,-1,null);}
 public MobileRelease(String version,String notes,long size,String sha256){this.version=version;this.notes=notes;this.size=size;this.sha256=normalizeDigest(sha256);download=REPO+"/releases/download/v"+version+"/"+asset(version);}
 public static String asset(String version){return "Codex-Mobile-Bridge-"+version+"-Android.apk";}
 public static String channel(String version){Matcher match=VERSION.matcher(version);if(!match.matches())throw new IllegalArgumentException("Invalid version");return match.group(4)==null?"stable":match.group(4);}
 public String page(){return REPO+"/releases/tag/v"+version;}
 private static String normalizeDigest(String value){if(value==null)return null;String digest=value.startsWith("sha256:")?value.substring(7):value;return digest.matches("[a-fA-F0-9]{64}")?digest.toLowerCase():null;}
 public static boolean isDownload(String url){try{String prefix=REPO+"/releases/download/v";if(!url.startsWith(prefix))return false;int slash=url.lastIndexOf('/');String version=url.substring(prefix.length(),slash);parts(version);return url.equals(new MobileRelease(version,"").download);}catch(Exception e){return false;}}
 public static boolean redirectAllowed(String url){try{java.net.URI value=new java.net.URI(url);String host=value.getHost();return "https".equalsIgnoreCase(value.getScheme())&&value.getRawUserInfo()==null&&host!=null&&(host.equalsIgnoreCase("github.com")||host.equalsIgnoreCase("objects.githubusercontent.com")||host.equalsIgnoreCase("release-assets.githubusercontent.com")||host.equalsIgnoreCase("github-releases.githubusercontent.com"));}catch(Exception e){return false;}}
 private static long[] parts(String value){
  Matcher m=VERSION.matcher(value);if(!m.matches())throw new IllegalArgumentException("Invalid version");
  int stage=m.group(4)==null?4:java.util.Arrays.asList("alpha","beta","preview","rc").indexOf(m.group(4));
  return new long[]{Long.parseLong(m.group(1)),Long.parseLong(m.group(2)),Long.parseLong(m.group(3)),stage,Long.parseLong(m.group(5)==null?"0":m.group(5))};
 }
 public static int compare(String a,String b){long[] x=parts(a),y=parts(b);for(int i=0;i<x.length;i++)if(x[i]!=y[i])return Long.compare(x[i],y[i]);return 0;}
 public static boolean eligible(String current,String tag,boolean draft,boolean prerelease,String name,String url){
  try{
   if(draft||!tag.startsWith("v"))return false;String v=tag.substring(1);
   if(!current.contains("-")&&(prerelease||v.contains("-")))return false;
   return compare(v,current)>0&&name.equals(asset(v))&&url.equals(new MobileRelease(v,"").download);
  }catch(RuntimeException e){return false;}
 }
}
