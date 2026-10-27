# A plain fedora "desktop" for packaging/linux_check.sh (packaging/linux/build_in_docker.sh): the libraries a desktop has, nothing extra.
FROM fedora:41
RUN dnf -y install --setopt=install_weak_deps=False xorg-x11-server-Xvfb xwd ImageMagick mesa-libGL mesa-libEGL \
    libxkbcommon-x11 nss libXcomposite libXdamage libXrandr libXtst alsa-lib dbus-libs fontconfig glib2 dejavu-sans-fonts \
    xcb-util-wm xcb-util-image xcb-util-keysyms xcb-util-renderutil xdg-utils findutils procps-ng && dnf clean all
RUN useradd -m player
USER player
WORKDIR /home/player
