#!/usr/bin/perl
use strict;
use warnings;
use IPC::Open3;
use IO::Select;
use Symbol 'gensym';
use Getopt::Long;
use Time::HiRes qw(time sleep);

# =============================================================
# Text2SIP pjsua call driver (PoC)
# Ersetzt sipcmd: registriert, ruft an, spielt WAV NACH CONFIRMED,
# wertet DTMF aus (RFC2833 UND SIP INFO), legt auf.
# Event-gesteuert: reagiert auf pjsua-Zustandsereignisse statt auf
# feste Wartezeiten fuer den CONFIRMED-Uebergang.
# =============================================================

my %o = (
    bin=>'', bound=>'', proxy=>'', user=>'', authuser=>'', password=>'',
    display=>'', called=>'', wav=>'',
    pause_before=>0, pause_after=>4000, timeout=>60,
    confirm_digit=>'-', result_url=>'', log=>'', debug=>0,
);
GetOptions(\%o,
    'bin=s','bound=s','proxy=s','user=s','authuser=s','password=s',
    'display=s','called=s','wav=s',
    'pause_before=i','pause_after=i','timeout=i',
    'confirm_digit=s','result_url=s','log=s','debug=i',
) or die "bad args\n";
$o{authuser} = $o{user} if !defined $o{authuser} || $o{authuser} eq '';

# --- Logging ---
my $LOG;
if ($o{log} ne '') { open $LOG, '>>', $o{log} or undef $LOG; if ($LOG) { $LOG->autoflush(1); } }
sub logline {
    my $m = shift;
    my $ts = scalar localtime;
    print STDERR "[pjsua_call] $m\n";
    print $LOG "$ts [pjsua_call] $m\n" if $LOG;
}

# --- WAV-Laenge (fuer einmalige Wiedergabe; --play-file loopt sonst) ---
# ffprobe is shipped with ffmpeg in the LoxBerry standard image.
# Use list-form open so the WAV path is never interpreted by a shell.
my $wav_dur = 0;
if ($o{wav} ne '' && -r $o{wav} && -x '/usr/bin/ffprobe') {
    if (open my $probe, '-|', '/usr/bin/ffprobe',
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            $o{wav}) {
        my $d = <$probe>;
        close $probe;
        chomp $d if defined $d;
        $wav_dur = ($d && $d =~ /^[\d.]+$/) ? $d + 0 : 0;
    }
}
$wav_dur = 6 if $wav_dur <= 0;

# Timeout-Semantik wie Alt-sipcmd: --timeout ist die ANTWORT-/Wählzeit (Zeit bis
# CONFIRMED), NICHT die Gesamtdauer. Die pjsua-Gesamtdauer (--duration, Sicherheits-
# cap) wird aus Antwortzeit + pause_before + WAV-Länge + pause_after + Reserve berechnet.
my $answer_timeout = ($o{timeout} && $o{timeout} > 0) ? $o{timeout} : 60;
my $total_cap = int($answer_timeout + $o{pause_before}/1000.0 + $wav_dur + $o{pause_after}/1000.0 + 8);
logline("WAV-Dauer ${wav_dur}s, Ziel $o{called}, answer_timeout=${answer_timeout}s total_cap=${total_cap}s pause_before=$o{pause_before}ms pause_after=$o{pause_after}ms confirm=$o{confirm_digit}");

# --- pjsua-Argumente ---
my $iduri = $o{display} ne ''
    ? "\"$o{display}\" <sip:$o{user}\@$o{proxy}>"
    : "sip:$o{user}\@$o{proxy}";
my @cmd = (
    '/usr/bin/stdbuf', '-oL', '-eL',   # pjsua block-puffert stdout auf Pipe -> Zeilenpufferung erzwingen
    $o{bin},
    '--null-audio', '--no-tones',
    "--bound-addr=$o{bound}",
    '--registrar', "sip:$o{proxy}",
    '--id', $iduri,
    '--realm', '*',
    '--username', $o{authuser},
    '--password', $o{password},
    "--play-file=$o{wav}",
    "--duration=$total_cap",
    '--log-level=5', '--app-log-level=4',
);

# --- pjsua starten ---
my ($wtr, $rdr, $err);
$err = gensym;
my $pid = open3($wtr, $rdr, $err, @cmd);
$wtr->autoflush(1);
my $sel = IO::Select->new($rdr, $err);

# --- Zustand ---
my $registered   = 0;
my $call_placed  = 0;
my $call_placed_t = 0;
my $confirmed    = 0;
my $confirmed_t  = 0;
my $wav_port     = 1;
my $call_port    = 0;
my $connected    = 0;
my $connect_t    = 0;
my $disc_wav     = 0;
my $hangup_sent  = 0;
my @dtmf_digits  = ();
my $done         = 0;
my $start        = time;
my $deadline     = $start + $total_cap + 5;

sub send_cmd { my $c = shift; print $wtr "$c\n"; logline("-> $c"); }

sub place_call {
    return if $call_placed;
    $call_placed = 1; $call_placed_t = time;
    send_cmd('m');
    send_cmd("sip:$o{called}\@$o{proxy}");
    logline("Anruf platziert");
}
sub connect_wav {
    return if $connected;
    $connected = 1; $connect_t = time;
    send_cmd('cc'); sleep 0.2; send_cmd($wav_port); sleep 0.2; send_cmd($call_port);
    logline("WAV(#$wav_port) -> Call(#$call_port) verbunden (nach CONFIRMED)");
}
sub disconnect_wav {
    return if $disc_wav || !$connected;
    $disc_wav = 1;
    send_cmd('cd'); sleep 0.2; send_cmd($wav_port); sleep 0.2; send_cmd($call_port);
    logline("WAV getrennt (Wiedergabe einmal durch)");
}
sub hangup {
    return if $hangup_sent;
    $hangup_sent = 1;
    send_cmd('h'); sleep 0.3; send_cmd('q');
    logline("Auflegen + Beenden");
}
sub fire_result {
    my $digit = shift;
    return if $o{result_url} eq '';
    system('wget','-q','-t','1','-T','10','-O','/dev/null', $o{result_url}.$digit);
    # Basic-Auth-Zugangsdaten (user:pass@host) im Log maskieren
    (my $masked = $o{result_url}.$digit) =~ s{(https?://[^:/\@]+:)[^\@/]*(\@)}{${1}***${2}}i;
    logline("Result-URL: $masked");
}

while (!$done) {
    if (!$hangup_sent && time > $deadline) { logline("Deadline -> auflegen"); hangup(); }

    # Antwort-Timeout: keine Rufannahme (CONFIRMED) innerhalb der Waehlzeit -> aufgeben
    if ($call_placed && !$confirmed && !$hangup_sent
        && (time - $call_placed_t) >= $answer_timeout) {
        logline("Keine Rufannahme innerhalb ${answer_timeout}s -> auflegen");
        hangup();
    }

    # NACH CONFIRMED: pause_before abwarten, dann WAV verbinden
    if ($confirmed && !$connected && $call_port > 0
        && (time - $confirmed_t) >= $o{pause_before}/1000.0) {
        connect_wav();
    }
    # Wiedergabe einmal durch -> WAV trennen
    if ($connected && !$disc_wav && (time - $connect_t) >= $wav_dur) {
        disconnect_wav();
    }
    # Wiedergabe + pause_after -> auflegen
    if ($disc_wav && !$hangup_sent
        && (time - $connect_t) >= ($wav_dur + $o{pause_after}/1000.0)) {
        hangup();
    }

    foreach my $fh ($sel->can_read(0.2)) {
        my $line = <$fh>;
        if (!defined $line) { $sel->remove($fh); next; }
        chomp $line;
        print $LOG "$line\n" if $LOG && $o{debug};

        if (!$registered && $line =~ /registration success, status=200/) {
            $registered = 1; logline("Registrierung 200 OK"); place_call();
        }
        if ($call_port == 0 && $line =~ /Add(?:ed)? port (\d+) \(sip:/) {
            $call_port = $1; logline("Call-Port erkannt: #$call_port");
        }
        if ($line =~ /Player created, id=\d+, slot=(\d+)/) { $wav_port = $1; }
        if (!$confirmed && $line =~ /state changed to CONFIRMED/) {
            $confirmed = 1; $confirmed_t = time; logline("CONFIRMED");
        }
        # Diagnose: jede echte DTMF-bezogene Zeile roh mitschreiben (nicht das Startmenue)
        if ($line =~ /dtmf/i && $line !~ /Send RFC 2833 DTMF|Send DTMF with INFO/) {
            logline("RAW-DTMF: $line");
        }
        # Echter DTMF-Empfang: RFC2833/INFO melden pjsua als "Incoming DTMF on call N: X".
        # Verhalten 1:1 aus altem sipcmd-$check_result portiert:
        #   - bei JEDER Ziffer: RESULT_VI + Ziffer feuern
        #   - Ziffer == Bestaetigungsziffer -> auflegen
        if ($line =~ /Incoming DTMF on call \d+:\s*([0-9A-D\*\#])/i) {
            my $digit = $1;
            push @dtmf_digits, $digit;
            logline("DTMF empfangen: $digit");
            fire_result($digit);
            if ($o{confirm_digit} ne '' && $o{confirm_digit} ne '-' && $digit eq $o{confirm_digit}) {
                logline("Bestaetigungsziffer '$digit' erkannt -> auflegen");
                hangup();
            }
        }
        if ($line =~ /Call \d+ is DISCONNECTED/ || $line =~ /state changed to DISCONNECTED/) {
            logline("DISCONNECTED"); hangup();
        }
    }

    if (waitpid($pid, 1) == $pid) { $done = 1; }  # WNOHANG (POSIX 1)
}

eval { close $wtr; };
1 while waitpid(-1, 1) > 0;

# Alt-Verhalten (sipcmd "Exiting."-Zweig): beim Beenden RESULT_VI + "0" feuern
if ($o{result_url} ne '') {
    fire_result('0');
}

logline(scalar(@dtmf_digits) . " DTMF-Ziffern empfangen: " . join('', @dtmf_digits));
logline("Fertig.");
exit 0;
