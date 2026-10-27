# The box the Linux program is built in (packaging/build.sh). Ubuntu 22.04, so the program runs on systems with
# glibc 2.35 or newer; Python 3.12 from the deadsnakes archive. The X / GL / NSS libraries are here so PyInstaller
# finds what Qt WebEngine links to (libxcb-cursor0 goes inside: Qt 6.5+ needs it and many systems lack it).
#   docker build -t legacy-linux-build packaging/linux
FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends software-properties-common gpg-agent ca-certificates \
    && add-apt-repository -y ppa:deadsnakes/ppa && apt-get update && apt-get install -y --no-install-recommends \
    python3.12 python3.12-venv python3.12-dev python3.12-tk binutils git \
    libxcb-cursor0 libxkbcommon-x11-0 libxkbcommon0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 \
    libxcb-render-util0 libxcb-shape0 libxcb-xinerama0 libxcb-xkb1 libxcb-xfixes0 libgl1 libegl1 libgbm1 libnss3 \
    libxcomposite1 libxdamage1 libxrandr2 libxtst6 libxi6 libxkbfile1 libxshmfence1 libasound2 libdbus-1-3 \
    libfontconfig1 libglib2.0-0 libatomic1 libwayland-client0 libwayland-cursor0 libwayland-egl1 libpulse0 libpulse-mainloop-glib0 \
    && rm -rf /var/lib/apt/lists/*
ENV PYTHON=python3.12
WORKDIR /src
