#!/usr/bin/env bash
# BC-250 gaming/console setup + core/CU unlock.  Run:  sudo bash ~/bc250/setup.sh
set -uo pipefail
R=$HOME/bc250
say(){ printf '\n\033[1;36m== %s\033[0m\n' "$*"; }
ok(){ printf '  \033[32m[ok]\033[0m %s\n' "$*"; }
bad(){ printf '  \033[31m[!!]\033[0m %s\n' "$*"; }

say "PHASE 1/6  packages: fastfetch + gaming stack"
pacman -Sy --needed --noconfirm fastfetch cachyos-gaming-meta cachyos-gaming-applications \
  gamemode lib32-gamemode mangohud lib32-mangohud goverlay \
  vulkan-radeon lib32-vulkan-radeon 2>&1 | tail -12 && ok "packages done" || bad "package install had errors"

say "PHASE 2/6  console behaviour: autologin, no suspend"
systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target >/dev/null 2>&1 && ok "suspend masked"
mkdir -p /etc/sddm.conf.d
cat > /etc/sddm.conf.d/10-autologin.conf <<'EOF'
[Autologin]
User=YOUR_USER
Session=plasma
Relogin=false
EOF
ok "autologin -> boots straight to desktop (screen locker already disabled)"

say "PHASE 3/6  8-core unlock"
cd "$R/bc250-core-cu-unlock" || { bad "repo missing"; exit 1; }
echo "--- before ---"; ./bc250-8core-unlock.sh status 2>&1 | tail -4
./bc250-8core-unlock.sh apply 2>&1 | tail -6
./bc250-8core-unlock.sh install 2>&1 | tail -4 && ok "persistence unit installed"

say "PHASE 4/6  ACPI tables for 8 cores (C-states for the new threads)"
./bc250-acpi-fix.sh install 2>&1 | tail -8 && ok "acpi tables installed" || bad "acpi fix failed"

say "PHASE 5/6  40CU re-apply"
/usr/local/bin/bc250-cu-live-manager --yes apply 2>&1 | tail -5

say "PHASE 6/6  verify"
echo "--- actual CU map ---"
"$R/bc250-40cu-unlock/scripts/cu_map.sh" 2>&1 | tail -8
echo "--- cpu ---"
echo "  online now  : $(nproc)   (cores appear after reboot)"
echo "  present     : $(cat /sys/devices/system/cpu/present)"
echo "--- installed ---"
for b in fastfetch steam mangohud gamemoderun; do printf "  %-12s %s\n" "$b" "$(command -v $b >/dev/null && echo yes || echo MISSING)"; done

printf '\n\033[1;33mNow:  sudo reboot     <-- WARM reboot. Do NOT cut power or the cores revert.\033[0m\n\n'
