//go:build tools

package tsnet

// Keep the gomobile Java binding runtime in the module graph so a pinned
// gomobile release can generate and compile the Android AAR reproducibly.
import _ "golang.org/x/mobile/bind"
