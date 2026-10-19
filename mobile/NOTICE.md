# Mobile companion preview

Copyright (c) 2026 try2love. Project code is covered by the repository MIT license.

Android QR scanning uses ZXing Core 3.5.3, Copyright ZXing authors, Apache License 2.0:
Full license: `licenses/ZXing-LICENSE.txt` (bundled in the APK as `assets/ZXing-LICENSE.txt`).
Upstream: https://github.com/zxing/zxing/blob/zxing-3.5.3/LICENSE

The embedded Tailscale Android node uses AndroidX WebKit 1.17.1, AndroidX Core 1.1.0,
AndroidX Annotation 1.8.1, AndroidX Annotation Experimental 1.3.0, JSpecify 1.0.0,
and Kotlin standard library 1.7.10, Copyright their respective authors,
Apache License 2.0:
Full license: `licenses/AndroidX-LICENSE.txt` (bundled in the APK as `assets/AndroidX-LICENSE.txt`).
Upstream: https://developer.android.com/jetpack/androidx

The embedded Tailscale Android node includes Tailscale 1.104.1 and a gomobile-generated
Java bridge, copyright Tailscale Inc. & contributors and The Go Authors,
BSD 3-Clause License:
Full licenses and dependency notices: `licenses/Tailscale-LICENSE.txt`,
`licenses/gomobile-LICENSE.txt`, and `tsnet/third_party/tailscale/licenses/android.md`
(bundled in the APK with matching `assets/` names).
Upstreams: https://github.com/tailscale/tailscale and https://go.googlesource.com/mobile

The apps use the existing Codex Mobile Bridge web client. No code or prebuilt packages from the two reviewed derivative apps are included.
