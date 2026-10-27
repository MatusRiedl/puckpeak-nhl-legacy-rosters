# A plain arch "desktop" for packaging/linux_check.sh (packaging/linux/build_in_docker.sh): the libraries a desktop has, nothing extra.
FROM archlinux:latest
RUN pacman -Syu --noconfirm xorg-server-xvfb xorg-xwd imagemagick mesa libxkbcommon-x11 nss libxcomposite libxdamage \
    libxrandr libxtst alsa-lib dbus fontconfig glib2 ttf-dejavu xcb-util-wm xcb-util-image xcb-util-keysyms \
    xcb-util-renderutil xdg-utils && pacman -Scc --noconfirm
RUN useradd -m player
USER player
WORKDIR /home/player
