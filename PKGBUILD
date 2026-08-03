# Maintainer: Berk Küçük <berkkucukk@proton.me>
#
# maze-branding — the Maze Linux visual identity: Plymouth boot theme, SDDM
# OLED login theme, wallpapers, logos and the fastfetch ASCII logo. Extracted
# from the ISO's airootfs overlay into a pacman package.
#
# Payload lives verbatim under ./maze-branding/ (a mirror of the target
# filesystem); package() copies it into $pkgdir.
#
# Deliberately NOT shipped here (special cases, kept as ISO build glue):
#   * /usr/lib/os-release        — owned by the `filesystem` package; overriding
#                                   it is done by the 0500-maze-os-release build
#                                   hook, not a package (would file-conflict).
#   * 10-maze-autologin.conf      — live-medium only (auto-logs the live user);
#                                   never wanted on an installed system.

pkgname=maze-branding
pkgver=1.3.0
pkgrel=1
pkgdesc="Maze Linux branding — Plymouth theme, SDDM OLED theme, wallpapers, logos, fastfetch logo"
arch=('any')
url="https://mazelinux.berkkucukk.com.tr"
license=('GPL3')
depends=()
optdepends=(
  'plymouth: boot splash theme'
  'sddm: OLED login theme'
  'fastfetch: shows the Maze ASCII logo'
)
# The SDDM theme selection is admin-tunable; preserve edits across upgrades.
backup=(
  'etc/sddm.conf.d/20-maze-theme.conf'
)
source=()

package() {
  cp -a "${startdir}/maze-branding/etc" "${pkgdir}/etc"
  cp -a "${startdir}/maze-branding/usr" "${pkgdir}/usr"

}
