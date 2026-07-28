# Troubleshooting

- **DISK_GUARD_PAUSE (20):** free space approached reserve; free disk or lower batch cap, then `.\bhava.ps1 resume`
- **Source drift (22):** table columns changed; update adapter fixtures and parser
- **Access restricted (23):** do not bypass; leave resource inaccessible
- **uv missing:** install from https://docs.astral.sh/uv/getting-started/installation/
- **Partial downloads:** `.part` files in `data/staging` are resumed automatically
