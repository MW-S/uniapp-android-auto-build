# syntax=docker/dockerfile:1.6
# ============================================================================
#  uniapp-android-auto-build Docker image (Linux amd64/arm64).
#
#  What is included:
#   - Python 3.12 + venv-less pip requirements (for runner / Feishu bot / Web UI)
#   - Node.js 20 LTS + npm (for uni-app "npm run build:app")
#   - OpenJDK 17 (required by AGP 8.7 used by the two real shell projects)
#   - Android SDK: commandlinetools + pre-installed
#         platforms;android-35 / build-tools;35.0.0 / platform-tools
#     AND the ability to install anything else on-demand via
#     `docker/ensure-android-env.sh` when a shell project declares a
#     different compileSdk / buildToolsVersion / ndkVersion.
#
#  Important: the image does NOT ship with your uni-app source code, your
#  Android shell project, your Feishu/KodCloud credentials or your Gradle
#  cache. Mount them at runtime via docker-compose volumes (see compose file).
# ============================================================================

FROM python:3.12-slim AS base

# Non-interactive apt, force UTF-8, shared Python bytecode location
ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# ---------- 1) System packages --------------------------------------------
#   - ca-certificates/curl/gnupg: to add the NodeSource APT repo
#   - git: pipeline step #1 (`git pull`)
#   - unzip/file: Android command line tools + general inspection
#   - procps/psmisc: Gradle watchdog / process listing during troubleshooting
#   - openjdk-17: AGP 8.x requires JDK 17
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        gnupg \
        lsb-release \
        git \
        unzip \
        file \
        procps \
        psmisc \
        locales \
        openjdk-17-jdk-headless \
 && rm -rf /var/lib/apt/lists/* \
 && localedef -i en_US -c -f UTF-8 -A /usr/share/locale/locale.alias en_US.UTF-8 || true

ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-$(uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/')
# Fallback (works regardless of uname -m because update-alternatives normalises it):
RUN if [ ! -x "${JAVA_HOME}/bin/java" ]; then \
        ALT=$(update-alternatives --list java 2>/dev/null | grep java-17-openjdk | head -n1 || true); \
        if [ -n "$ALT" ]; then export JAVA_HOME=$(dirname $(dirname "$ALT")); fi; \
    fi \
 && [ -x "${JAVA_HOME}/bin/java" ] \
 && echo "JAVA_HOME=$JAVA_HOME" >> /etc/environment

# ---------- 2) Node.js 20 LTS via NodeSource --------------------------------
RUN set -eu; \
    KEYRING=/usr/share/keyrings/nodesource.gpg; \
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor --yes -o "$KEYRING"; \
    DISTRO=$(lsb_release -cs 2>/dev/null || echo bookworm); \
    echo "deb [signed-by=$KEYRING] https://deb.nodesource.com/node_20.x nodistro main" > /etc/apt/sources.list.d/nodesource.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends nodejs; \
    rm -rf /var/lib/apt/lists/*; \
    node -v; npm -v

# ---------- 3) Android SDK command-line tools + pre-installed packages ------
# Versions here match the two verified real shell projects:
#   AGP 8.7.3 + Gradle 8.11.1 + compileSdk 35 + buildTools 35.0.0, NO NDK.
ENV ANDROID_SDK_ROOT=/opt/android-sdk \
    ANDROID_HOME=/opt/android-sdk \
    ANDROID_COMPILE_SDK=35 \
    ANDROID_BUILD_TOOLS=35.0.0 \
    CMDLINE_TOOLS_VERSION=11076708
ENV PATH=${ANDROID_SDK_ROOT}/cmdline-tools/latest/bin:${ANDROID_SDK_ROOT}/platform-tools:${PATH}

RUN set -eu; \
    mkdir -p "${ANDROID_SDK_ROOT}/cmdline-tools" "${ANDROID_SDK_ROOT}/licenses" "$HOME/.android"; \
    # The official, stable URL pattern. Version 11076708 is "12.0 cmdline-tools".
    URL="https://dl.google.com/android/repository/commandlinetools-linux-${CMDLINE_TOOLS_VERSION}_latest.zip"; \
    curl -fsSL "$URL" -o /tmp/cmdline-tools.zip; \
    unzip -q /tmp/cmdline-tools.zip -d /tmp/cmdline; \
    mv /tmp/cmdline/cmdline-tools "${ANDROID_SDK_ROOT}/cmdline-tools/latest"; \
    rm -rf /tmp/cmdline /tmp/cmdline-tools.zip; \
    # Pre-accept the SDK license so `sdkmanager --install` is non-interactive.
    printf '\n24333f8a63b6825ea9c5514f83c2829b004d1fee\n' > "${ANDROID_SDK_ROOT}/licenses/android-sdk-license"; \
    # sdkmanager itself is a Java tool; make sure JAVA_HOME is visible to it.
    export JAVA_HOME; \
    yes 2>/dev/null | sdkmanager --sdk_root="${ANDROID_SDK_ROOT}" --licenses >/dev/null || true; \
    sdkmanager --sdk_root="${ANDROID_SDK_ROOT}" --install \
        "platforms;android-${ANDROID_COMPILE_SDK}" \
        "build-tools;${ANDROID_BUILD_TOOLS}" \
        "platform-tools"; \
    sdkmanager --sdk_root="${ANDROID_SDK_ROOT}" --list >/tmp/sdk-list.txt 2>&1; \
    # Sanity checks
    [ -d "${ANDROID_SDK_ROOT}/platforms/android-${ANDROID_COMPILE_SDK}" ]; \
    [ -d "${ANDROID_SDK_ROOT}/build-tools/${ANDROID_BUILD_TOOLS}" ]; \
    [ -x "${ANDROID_SDK_ROOT}/platform-tools/adb" ]; \
    rm -f /tmp/sdk-list.txt

# Gradle cache and npm cache live on mounted volumes (see compose), but make
# sure there's a sensible default location inside the container as well.
ENV GRADLE_USER_HOME=/opt/gradle-cache \
    NPM_CONFIG_CACHE=/opt/npm-cache
RUN mkdir -p "$GRADLE_USER_HOME" "$NPM_CONFIG_CACHE"

# ---------- 4) Copy project source + install Python requirements ------------
WORKDIR /app
COPY requirements.txt  /app/
RUN python -m pip install --upgrade pip setuptools wheel \
 && python -m pip install -r /app/requirements.txt

COPY . /app/
# ensure-android-env.sh must be executable inside the container
RUN chmod +x /app/docker/ensure-android-env.sh || true

# ---------- 5) Entrypoint: delegate to main.py (same as source mode) -------
# Common flags:
#   docker run ... uniapp-android-builder --run-once --project mes-pda
#   docker compose up (default CMD: "" -> `python main.py` -> Web + Feishu)
EXPOSE 8000
ENTRYPOINT ["python", "main.py"]
CMD []
