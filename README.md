# maze-branding

The **Maze Linux visual identity**, extracted from the ISO's `airootfs` overlay
into a pacman package.

## What's inside

| Path | Contents |
| ---- | -------- |
| `usr/share/plymouth/themes/maze/` | Plymouth boot-splash theme |
| `usr/share/sddm/themes/maze-oled/` | SDDM OLED login theme |
| `usr/share/wallpapers/Maze*` | Wallpaper set (`Maze`, `Maze1…9`, `MazeOLED`) |
| `usr/share/pixmaps/maze-logo.png`, `maze-simple-logo.png` | Shared logos used by the Maze GUI apps and `.desktop` icons |
| `usr/share/pixmaps/maze-user-avatar.png` | Default user avatar |
| `usr/share/maze/fastfetch-logo.txt` | Fastfetch ASCII logo |
| `etc/sddm.conf.d/20-maze-theme.conf` | Selects the SDDM OLED theme |

`maze-tools` depends on this package for the shared `maze-*-logo.png` files (they
used to be duplicated; they now live here to avoid a file conflict).

## Installation

> **Part of Maze Linux.** Every Maze Linux system already has it (pulled in by `maze-meta`). It is built around Maze's own system layout, so installing it on another distribution is not supported.

### From the Maze repository

**On Maze Linux** the repository is already configured:

```bash
sudo pacman -S maze-branding
```

**On Arch Linux and Arch-based distributions**, add the repository once:

1. Import and trust the Maze signing key:

   ```bash
   curl -O https://mazerepo.berkkucukk.com.tr/packages/mazelinux.gpg
   gpg --show-keys --with-fingerprint mazelinux.gpg
   sudo pacman-key --add mazelinux.gpg
   sudo pacman-key --lsign-key 7C4D515A6B930CB04794CEF6147C8159B3E2EE5F
   ```

   The fingerprint `gpg` prints must be `7C4D 515A 6B93 0CB0 4794  CEF6 147C 8159 B3E2 EE5F`.

2. Add the repository to the end of `/etc/pacman.conf`:

   ```ini
   [mazelinux]
   SigLevel = Required DatabaseOptional
   Server = https://mazerepo.berkkucukk.com.tr/packages
   ```

3. Sync and install:

   ```bash
   sudo pacman -Syu maze-branding
   ```

Optionally install `mazelinux-keyring` as well; it keeps the signing key up to date through pacman.

Remove with `sudo pacman -Rns maze-branding`.

### Build from source

```bash
sudo pacman -S --needed base-devel git
git clone https://github.com/berk-kucuk/maze-branding.git
cd maze-branding
makepkg -si
```

## Layout & building

```
maze-branding/
├── PKGBUILD  build.sh  README.md
└── maze-branding/   # payload — verbatim mirror of the target filesystem
    ├── etc/sddm.conf.d/...
    └── usr/share/...
```

```sh
./build.sh
./build.sh --repo ../MazeLinux/localrepo
```

## Deliberately NOT shipped here

- **`/usr/lib/os-release`** — owned by the base `filesystem` package. Overriding
  the distro identity is done by the `0500-maze-os-release` build hook, not a
  package (a package owning that path would file-conflict with `filesystem`).
- **`10-maze-autologin.conf`** — live-medium only (auto-logs the live user in);
  never wanted on an installed system, so it stays ISO build glue.
