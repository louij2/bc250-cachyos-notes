# Troubleshooting — real failures, in the order they happened

## Black screen with a moving mouse cursor

**Cause: a loose DisplayPort connector.**

Diagnostic value of the cursor: the hardware cursor is drawn on a *separate
plane* by the display controller. **If the cursor moves, your cable, monitor,
amdgpu driver and modeset are all working.** That rules out most of what people
chase first (`nomodeset`, Mesa, kernel regressions).

An unstable DP link generates repeated hotplug events. KDE reconfigures its
outputs on every one, and the desktop can end up on a phantom output — black
screen, cursor still live.

Escalating symptoms from the same single fault:

1. Black screen, cursor moves
2. Monitor flickering on and off — link dropping and re-training
3. Static / snow in the image — corrupted pixel data, i.e. bit errors on the link

Static plus flicker is a **physical-layer** signature. Stop debugging software.

Fix: reseat both ends until the latch clicks. Prefer native DP→DP. Passive
adapters behave better than active ones on this board.

## "Incorrect password" when the password is definitely right

**Cause: `pam_faillock`.** Arch/CachyOS defaults are `deny=3`,
`unlock_time=600`. Three fat-fingers at the KDE lock screen locks the account
for **ten minutes**, and every attempt in that window — `sudo` included — is
rejected with "incorrect password" rather than "account locked".

```bash
faillock --user "$USER"        # shows the failed attempts and timestamps
sudo faillock --user "$USER" --reset
```

The `Valid` column marks attempts still counting. Unlock time is
*last failure + `unlock_time`*.

To make it less trigger-happy on a console box:

```bash
printf 'deny = 10\nunlock_time = 120\n' | sudo tee -a /etc/security/faillock.conf
```

## Wired ethernet never gets an address

`ip -br a` showed `enp4s0` **UP** with a valid 1000Mb/s full-duplex link, but no
IP. `nmcli connection show` listed no profile for it at all.

NetworkManager will not touch an interface it has no profile for. Fix:

```bash
sudo nmcli connection add type ethernet ifname enp4s0 con-name wired-enp4s0 \
  autoconnect yes ipv4.method auto
sudo nmcli connection up wired-enp4s0
```

## Suspend takes the machine off the network

Not a bug. S3 suspend cuts power to everything except RAM self-refresh,
including the NIC — a sleeping machine cannot hold a DHCP lease or answer ARP.

For a box you want reachable over SSH:

```bash
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
```

Masking the targets is more reliable than fighting the desktop's power settings.

## SSH refused vs timed out — they mean different things

Worth internalising, it saves a lot of guessing:

| Symptom | Meaning |
|---|---|
| **Timeout** | Packets dropped — firewall `DROP`, or wrong host |
| **Connection refused** | Host reachable, nothing listening (or firewall `REJECT`) |
| **`Permission denied (publickey)`** | Reached sshd fine; auth failed. Also returned for *non-existent users*, so it does not tell you whether the account exists |

A firewall rule added to the **wrong firewalld zone** flips the symptom from
timeout to refused without actually permitting the port — the interface's zone
is what matters, not the default zone.

Also: `systemctl enable` can succeed while the service still fails to start.
Always confirm with `systemctl is-active` and `ss -tlnp | grep :22`.

## sshd config edits that appear to do nothing

Modern OpenSSH reads `/etc/ssh/sshd_config.d/*.conf`, the `Include` sits at the
**top** of `sshd_config`, and **the first value obtained wins**. A drop-in
therefore beats anything you edit into the main file.

```bash
sudo sshd -T | grep -i passwordauthentication   # effective value, after includes
```

To force a setting, use a drop-in that sorts first (`00-`).

## DHCP handing out addresses that are already in use

Leases showing `binding state abandoned` mean the client ARP-probed the offered
address, found it occupied, and sent a DHCPDECLINE. That is correct client
behaviour — it is the *server* that is wrong.

Cause: statically-configured hosts sitting **inside** the DHCP pool range.

Note for ISC dhcpd: a reservation inside the dynamic range is **not**
automatically excluded from that range. Keep reservations outside the pool.

## Tailscale `--accept-routes` sending local LAN traffic through the tunnel

If another node on your tailnet advertises a subnet route for the LAN the
BC-250 is **already physically on**, and the BC-250 has `--accept-routes`
enabled, the box will install that route and send traffic to its own local
subnet over `tailscale0` instead of out of the NIC.

Everything still works, which is why this hides — it just gets slower, and
anything bandwidth-sensitive on the LAN (a LanCache instance, a NAS, local
game streaming) quietly loses most of its throughput.

Check where local traffic actually goes:

```bash
ip -o route get <local-ip> | awk '{for(i=1;i<=NF;i++) if($i=="dev") print $(i+1)}'
# want: your ethernet interface.  bad: tailscale0
tailscale debug prefs | grep RouteAll
```

Fix — a host that is physically on the subnet does not need a route to it:

```bash
sudo tailscale set --accept-routes=false
```

Measured on this box, a LanCache request went from traversing the tunnel to
`200 in 0.0015s` straight over the wire.

Only enable `--accept-routes` on nodes that are genuinely *remote* from the
subnets being advertised.

## Governor shipped throttling at the temperature that causes crashes

Worth checking on any BC-250, because the default is not conservative.

`cyan-skillfish-governor-smu` config as deployed here had:

```toml
[temperature]
throttling = 90
throttling_recovery = 82
```

The hardware docs state that above 85 °C the system may throttle, and **above
90 °C instability and crashes occur**. So the governor was configured not to
back off until the GPU had already reached the temperature at which the board
is documented to fall over.

This is a strong candidate for unexplained hard-locks that leave nothing in the
logs — a thermal lock-up kills the machine before anything is written to disk,
so it looks identical to "it just died".

The documented values:

```toml
[temperature]
throttling = 85
throttling_recovery = 75
```

```bash
sudo systemctl restart cyan-skillfish-governor-smu
```

Check yours before assuming it is sane:

```bash
grep -A3 '\[temperature\]' /etc/cyan-skillfish-governor-smu/config.toml
```
