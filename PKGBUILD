# Maintainer: Berk Küçük <dev.berkkucukk@gmail.com>
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
pkgver=1.6.1
pkgrel=4
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
  # ── Adopted from the ISO's airootfs (2026-09) ──────────────────────────────
  # These used to exist only in the live image, so installed machines carried
  # them UNOWNED and no update ever reached them. They are in backup=() so the
  # takeover is silent: pacman does not treat an existing unowned file that the
  # package lists as a backup as a conflict — an identical copy is simply
  # adopted, a locally edited one is kept and the packaged one lands as .pacnew.
  # Without this, `pacman -Syu` on every installed Maze would stop with
  # "exists in filesystem" until the user ran --overwrite by hand.
  'usr/share/icons/hicolor/128x128/apps/mazelinux.png'
  'usr/share/icons/hicolor/256x256/apps/mazelinux.png'
  'usr/share/icons/hicolor/512x512/apps/mazelinux.png'
  'usr/share/sddm/themes/breeze/theme.conf.user'
)
source=()

package() {
  cp -a "${startdir}/maze-branding/etc" "${pkgdir}/etc"
  cp -a "${startdir}/maze-branding/usr" "${pkgdir}/usr"

}
