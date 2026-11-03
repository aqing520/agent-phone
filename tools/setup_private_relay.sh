#!/bin/bash
# Run as root on Ubuntu. First argument: endpoint IP; public tunnel key on stdin.
set -euo pipefail
endpoint=${1:?Usage: setup_private_relay.sh PUBLIC_IP < tunnel.pub}
IFS= read -r tunnel_key
[[ "$endpoint" =~ ^[0-9.]+$ ]] || { echo 'Expected IPv4 endpoint'; exit 1; }
[[ "$tunnel_key" == ssh-ed25519\ * ]] || { echo 'Expected Ed25519 public key'; exit 1; }
command -v wg >/dev/null
command -v qrencode >/dev/null
umask 077
install -d -m 700 /etc/wireguard /etc/agent-phone
# Preserve existing keys and phone pairing on repeat runs.
if [[ ! -f /etc/wireguard/apwg0.conf ]]; then
    server_key=$(wg genkey)
    phone_key=$(wg genkey)
    server_pub=$(printf '%s' "$server_key" | wg pubkey)
    phone_pub=$(printf '%s' "$phone_key" | wg pubkey)
    psk=$(wg genpsk)
    cat > /etc/wireguard/apwg0.conf <<EOF
[Interface]
Address = 10.77.73.1/24
ListenPort = 51820
PrivateKey = $server_key

[Peer]
PublicKey = $phone_pub
PresharedKey = $psk
AllowedIPs = 10.77.73.2/32
EOF
    cat > /etc/agent-phone/phone.conf <<EOF
[Interface]
PrivateKey = $phone_key
Address = 10.77.73.2/32
MTU = 1280

[Peer]
PublicKey = $server_pub
PresharedKey = $psk
Endpoint = $endpoint:51820
AllowedIPs = 10.77.73.1/32
PersistentKeepalive = 25
EOF
fi
qrencode -r /etc/agent-phone/phone.conf -o /etc/agent-phone/phone-qr.png -s 8 -m 4
chmod 600 /etc/wireguard/apwg0.conf /etc/agent-phone/phone.conf /etc/agent-phone/phone-qr.png
if ! id agent-phone-tunnel >/dev/null 2>&1; then
    useradd --create-home --shell /usr/sbin/nologin agent-phone-tunnel
fi
install -d -m 700 -o agent-phone-tunnel -g agent-phone-tunnel /home/agent-phone-tunnel/.ssh
authorized=/home/agent-phone-tunnel/.ssh/authorized_keys
entry="restrict,port-forwarding,permitlisten=\"10.77.73.1:5173\" $tunnel_key"
touch "$authorized"
grep -qxF -- "$entry" "$authorized" || printf '%s\n' "$entry" >> "$authorized"
chown agent-phone-tunnel:agent-phone-tunnel "$authorized"
chmod 600 "$authorized"
cat > /etc/ssh/sshd_config.d/90-agent-phone.conf <<'EOF'
Match User agent-phone-tunnel
    AuthenticationMethods publickey
    PasswordAuthentication no
    KbdInteractiveAuthentication no
    AllowTcpForwarding remote
    AllowStreamLocalForwarding no
    GatewayPorts clientspecified
    PermitListen 10.77.73.1:5173
    PermitOpen none
    PermitTTY no
    X11Forwarding no
    AllowAgentForwarding no
    MaxSessions 0
    ClientAliveInterval 30
    ClientAliveCountMax 3
Match all
EOF
/usr/sbin/sshd -t
systemctl enable --now wg-quick@apwg0
systemctl reload ssh
echo 'Private relay installed. Allow inbound UDP 51820 in the cloud firewall.'
echo 'Dashboard: http://10.77.73.1:5173 (WireGuard connection required).'
