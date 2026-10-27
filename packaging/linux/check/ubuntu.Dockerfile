# A plain Ubuntu 24.04 "desktop" for packaging/linux_check.sh (packaging/linux/build_in_docker.sh): no WebKit, no libatomic, like many players.
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends xvfb x11-apps imagemagick ca-certificates curl \
    libgl1 libegl1 libgbm1 libxkbcommon-x11-0 libxkbcommon0 libnss3 libxcomposite1 libxdamage1 libxrandr2 libxtst6 libxi6 \
    libasound2t64 libdbus-1-3 libfontconfig1 libglib2.0-0t64 libgtk-3-0t64 fonts-dejavu-core xdg-utils \
    libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 libxcb-shape0 libxcb-xinerama0 libxcb-xkb1 \
    && rm -rf /var/lib/apt/lists/*
RUN useradd -m player
USER player
WORKDIR /home/player
