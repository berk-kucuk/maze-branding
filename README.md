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
