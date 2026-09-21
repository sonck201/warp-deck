#!/usr/bin/env bash
# Build WarpDeck and deploy it to a Decky Loader device (Bazzite / SteamOS).
# Edit the three vars below, then: ./scripts/deploy.sh
set -euo pipefail

DECK_USER="${DECK_USER:-bazzite}"
DECK_HOST="${DECK_HOST:-192.168.1.100}"   # IP or hostname
DECK_PORT="${DECK_PORT:-22}"
PLUGIN_DIR="${PLUGIN_DIR:-WarpDeck}"      # folder name under ~/homebrew/plugins
DECK_KEY="${DECK_KEY:-$HOME/.ssh/id_ed25519}"  # private key; run ssh-copy-id -i "$DECK_KEY.pub" ... once

cd "$(dirname "$0")/.."

yarn install --immutable
yarn build

SSH_OPTS="-p $DECK_PORT"
if [ -f "$DECK_KEY" ]; then SSH_OPTS="$SSH_OPTS -i $DECK_KEY -o IdentitiesOnly=yes"; fi
SSH="ssh -t $SSH_OPTS $DECK_USER@$DECK_HOST"
DEST="homebrew/plugins/$PLUGIN_DIR"

# wipe the old install (decky owns it as root) and hand the fresh dir to us for the rsync
$SSH "sudo rm -rf ~/homebrew/plugins/${PLUGIN_DIR:?} && sudo mkdir -p ~/$DEST && sudo chown -R $DECK_USER: ~/homebrew/plugins ~/$DEST"

rsync -az --delete -e "ssh $SSH_OPTS" \
  dist main.py package.json plugin.json py_modules defaults README.md LICENSE \
  "$DECK_USER@$DECK_HOST:$DEST/"

$SSH "sudo chown -R root:root ~/$DEST && sudo systemctl restart plugin_loader"

echo "Deployed to $DECK_USER@$DECK_HOST:~/$DEST — open QAM > Decky."
