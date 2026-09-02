#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# ensure-android-env.sh
#
# Make the Android build environment "self-align" with whatever the shell
# project actually declares. Run this BEFORE invoking ./gradlew inside a
# Docker container. The script is intentionally idempotent: running it
# multiple times for the same project is cheap.
#
# What it does:
#   1. Requires ANDROID_SDK_ROOT and JAVA_HOME are set (basic preflight).
#   2. Parses the nearest root-level build.gradle[.kts] for the Android
#      Gradle Plugin (AGP) version and warns if the pre-installed JDK is
#      not compatible.
#   3. Parses App/build.gradle[.kts] for compileSdk, buildToolsVersion and
#      ndkVersion. For any declared version that is missing under
#      $ANDROID_SDK_ROOT it calls `sdkmanager --install` once to install it.
#   4. Always ensures `platform-tools` is installed (adb etc).
#
# Usage (Docker entrypoint / pipeline step):
#   bash /app/docker/ensure-android-env.sh /path/to/android-shell-project
# ---------------------------------------------------------------------------
set -euo pipefail

log()  { printf '[ensure-android-env] %s\n' "$*"; }
warn() { printf '[ensure-android-env][WARN] %s\n' "$*" >&2; }
die()  { printf '[ensure-android-env][ERROR] %s\n' "$*" >&2; exit 1; }

if [ $# -lt 1 ]; then
    die "Usage: $0 <android-shell-project-dir>"
fi
PROJECT_DIR="$1"
[ -d "$PROJECT_DIR" ] || die "Shell project dir does not exist: $PROJECT_DIR"

# ---- 1) Basic env ---------------------------------------------------------
: "${ANDROID_SDK_ROOT:?Need ANDROID_SDK_ROOT (Docker images sets it to /opt/android-sdk)}"
: "${JAVA_HOME:?Need JAVA_HOME (Docker image pre-installs OpenJDK 17)}"

command -v sdkmanager >/dev/null 2>&1 \
    || die "sdkmanager not on PATH. Did you install Android cmdline-tools under \$ANDROID_SDK_ROOT?"

"$JAVA_HOME/bin/java" -version >/dev/null 2>&1 \
    || die "JAVA_HOME=$JAVA_HOME does not point to a working JDK"

mkdir -p "$ANDROID_SDK_ROOT" "$HOME/.android"
# Pre-accept the Google SDK licenses. Official container deployments mount a
# pre-signed license volume here. If a license is missing, sdkmanager will
# still prompt; passing `yes` handles that on first install.
ACCEPT_DIR="$ANDROID_SDK_ROOT/licenses"
mkdir -p "$ACCEPT_DIR"
echo -e "\n24333f8a63b6825ea9c5514f83c2829b004d1fee" > "$ACCEPT_DIR/android-sdk-license" 2>/dev/null || true

SDKMAN=(sdkmanager --sdk_root="$ANDROID_SDK_ROOT")

install_if_missing() {
    # $1 = sdkmanager package key; $2 = expected relative path under $ANDROID_SDK_ROOT
    local pkg="$1" rel="${2:-$1}"
    if [ ! -e "$ANDROID_SDK_ROOT/$rel" ]; then
        log "Installing missing SDK component: $pkg"
        yes 2>/dev/null | "${SDKMAN[@]}" --install "$pkg" >/tmp/sdkmanager.log 2>&1 || {
            tail -n 30 /tmp/sdkmanager.log >&2 || true
            die "Failed to install $pkg (see /tmp/sdkmanager.log)"
        }
        return 0
    fi
    log "Already installed: $pkg"
}

# Always make sure platform-tools is present (adb, aapt2 helpers, etc.)
install_if_missing "platform-tools" "platform-tools"

# ---- 2) Resolve AGP version from root build.gradle[.kts] -------------------
ROOT_GRADLE=""
for candidate in "$PROJECT_DIR/build.gradle" "$PROJECT_DIR/build.gradle.kts"; do
    [ -f "$candidate" ] && { ROOT_GRADLE="$candidate"; break; }
done
AGP_VERSION=""
if [ -n "$ROOT_GRADLE" ]; then
    AGP_VERSION=$(sed -E -n \
        's/.*com\.android\.tools\.build:gradle[ \t]*:+[ \t]*\x27?([0-9]+\.[0-9]+\.[0-9]+[^ \t\x27"]*).*/\1/ip' \
        "$ROOT_GRADLE" | head -n1 || true)
fi
log "Detected AGP version: ${AGP_VERSION:-<unknown>}"
if [ -n "$AGP_VERSION" ]; then
    AGP_MAJOR="${AGP_VERSION%%.*}"
    if [ "$AGP_MAJOR" -ge 9 ]; then
        warn "AGP $AGP_VERSION requires JDK >=21 for full compatibility (current JAVA_HOME=$JAVA_HOME, JDK17). Build may fail; please extend the Docker image with JDK 21."
    elif [ "$AGP_MAJOR" = "8" ]; then
        : # happy path: AGP 8.x requires JDK 17 which is what we ship.
    elif [ "$AGP_MAJOR" = "7" ]; then
        warn "AGP $AGP_VERSION works best with JDK 11. Current JDK17 is fine for most builds but please report any JDK compatibility errors."
    elif [ "$AGP_MAJOR" -le 6 ]; then
        warn "AGP $AGP_VERSION is very old and usually requires JDK 8/11. JDK 17 may not be compatible."
    fi
fi

# ---- 3) Resolve App-level compileSdk / buildToolsVersion / ndkVersion -------
APP_GRADLE=""
for d in "$PROJECT_DIR/App/build.gradle" "$PROJECT_DIR/App/build.gradle.kts" \
         "$PROJECT_DIR/app/build.gradle" "$PROJECT_DIR/app/build.gradle.kts"; do
    [ -f "$d" ] && { APP_GRADLE="$d"; break; }
done
[ -n "$APP_GRADLE" ] || die "Cannot locate App/app build.gradle under $PROJECT_DIR"
log "Parsing $APP_GRADLE"

# compileSdk / compileSdkVersion
COMPILE_SDK=$(sed -E -n \
    's/^[[:space:]]*compileSdk(Version)?[[:space:]]+["'"'"']?([0-9]{2,3})["'"'"']?.*$/\2/ip' \
    "$APP_GRADLE" | head -n1 || true)
if [ -z "$COMPILE_SDK" ]; then
    die "Could not determine compileSdk from $APP_GRADLE"
fi
log "Detected compileSdk = $COMPILE_SDK"
install_if_missing "platforms;android-$COMPILE_SDK" "platforms/android-$COMPILE_SDK"

# buildToolsVersion (optional; if omitted Android Gradle Plugin picks its own
# default version, which is always covered if we install the latest for the
# current compileSdk). We only install what the user explicitly declared.
BUILD_TOOLS=$(sed -E -n \
    "s/^[[:space:]]*buildToolsVersion[[:space:]]+[\"\x27]?([0-9]+\.[0-9]+\.[0-9]+(?:[_-][a-zA-Z0-9]+)?)[\"\x27]?.*\$/\1/ip" \
    "$APP_GRADLE" | head -n1 || true)
if [ -n "$BUILD_TOOLS" ]; then
    log "Detected buildToolsVersion = $BUILD_TOOLS"
    install_if_missing "build-tools;$BUILD_TOOLS" "build-tools/$BUILD_TOOLS"
else
    log "No buildToolsVersion declared; Android Gradle Plugin will pick its default."
fi

# ndkVersion (optional)
NDK_VERSION=$(sed -E -n \
    "s/^[[:space:]]*ndkVersion[[:space:]]+[\"\x27]?([^\"'\x27,]+)[\"\x27]?.*\$/\1/ip" \
    "$APP_GRADLE" | head -n1 || true)
if [ -n "$NDK_VERSION" ]; then
    log "Detected ndkVersion = $NDK_VERSION"
    install_if_missing "ndk;$NDK_VERSION" "ndk/$NDK_VERSION"
else
    log "No ndkVersion declared; NDK is not required."
fi

# ---- 4) Print a short sanity summary ---------------------------------------
log "Android SDK ready at $ANDROID_SDK_ROOT"
log "  platforms/android-$COMPILE_SDK: $([ -d "$ANDROID_SDK_ROOT/platforms/android-$COMPILE_SDK" ] && echo OK || echo MISSING)"
if [ -n "$BUILD_TOOLS" ]; then
    log "  build-tools/$BUILD_TOOLS: $([ -d "$ANDROID_SDK_ROOT/build-tools/$BUILD_TOOLS" ] && echo OK || echo MISSING)"
fi
log "  platform-tools: $([ -d "$ANDROID_SDK_ROOT/platform-tools" ] && echo OK || echo MISSING)"
