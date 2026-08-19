#!/usr/bin/env bash
set -u

CODE_BASE="REPLACELBHOMEDIR/bin/plugins/text2sip/pockettts"
DATA_BASE="REPLACELBHOMEDIR/data/plugins/text2sip/pockettts"
VENV="$DATA_BASE/venv"
CLI="$VENV/bin/pocket-tts"
CACHE="$DATA_BASE/cache"
STATE="$DATA_BASE/languages"
TMPBASE="/run/shm/text2sip-pockettts"
LOG="REPLACELBHOMEDIR/log/plugins/text2sip/Text2SIP.log"
VERBOSE="${POCKETTTS_STDOUT:-0}"

mkdir -p "$CACHE" "$STATE" "$TMPBASE" 2>/dev/null || true

log() {
    local line
    line="$(date '+%F %T') $*"
    if [ "$VERBOSE" = "1" ]; then
        printf '%s\n' "$line"
    else
        printf '%s\n' "$line" >> "$LOG" 2>/dev/null || true
    fi
}

code="${2:-${1:-}}"
action="${1:-install}"
if [ "$action" != "install" ] && [ "$action" != "status" ]; then
    code="$action"
    action="install"
fi
code="$(printf '%s' "$code" | tr '[:upper:]' '[:lower:]')"

# Text2SIP prefers Pocket-TTS' compact/low layer variants. Pocket-TTS 2.1.0
# provides French only as french_24l, so French is the one deliberate exception.
case "$code" in
    de|de-de) canon="de"; model="german";     voice="juergen";  warmtext="Test" ;;
    gb|us|en|en-gb|en-us) canon="en"; model="english"; voice="alba"; warmtext="Test" ;;
    es|es-es) canon="es"; model="spanish";    voice="lola";     warmtext="Prueba" ;;
    it|it-it) canon="it"; model="italian";    voice="giovanni"; warmtext="Prova" ;;
    pt|pt-pt) canon="pt"; model="portuguese"; voice="rafael";   warmtext="Teste" ;;
    fr|fr-fr) canon="fr"; model="french_24l"; voice="estelle"; warmtext="Bonjour" ;;
    *)
        log "<WARNING> Pocket-TTS: unsupported language code '$code'"
        exit 2
        ;;
esac

marker="$STATE/$canon.ready"

if [ "$action" = "status" ]; then
    [ -f "$marker" ] && exit 0
    exit 1
fi

if [ -f "$marker" ] && [ -x "$CLI" ]; then
    log "<OK> Pocket-TTS language already prepared: $canon ($model/$voice)"
    exit 0
fi

if [ ! -x "$CLI" ]; then
    log "<ERROR> Pocket-TTS CLI missing: $CLI"
    exit 3
fi

out="$TMPBASE/warmup-${canon}-$$.wav"
rm -f "$out"

export HF_HOME="$CACHE/huggingface"
export HUGGINGFACE_HUB_CACHE="$CACHE/huggingface/hub"
export XDG_CACHE_HOME="$CACHE/xdg"
export TORCH_HOME="$CACHE/torch"
export TMPDIR="$TMPBASE"
export LC_ALL="C.UTF-8"
export LANG="C.UTF-8"

log "<INFO> Pocket-TTS: preparing language=$canon model=$model voice=$voice"

if "$CLI" generate \
    --language "$model" \
    --voice "$voice" \
    --text "$warmtext" \
    --output-path "$out" \
    --quiet >> "$LOG" 2>&1; then
    rc=0
else
    rc=$?
fi

if [ "$rc" -eq 0 ] && [ -s "$out" ]; then
    : > "$marker"
    chmod 664 "$marker" 2>/dev/null || true
    rm -f "$out"
    log "<OK> Pocket-TTS language ready: $canon ($model/$voice)"
    exit 0
fi

rm -f "$out"
log "<ERROR> Pocket-TTS language preparation failed: $canon ($model/$voice), exit=$rc"
exit 4
