#!/usr/bin/env perl
# =============================================================================
# mqtt_handshake_test.pl — Reliable handshake test for Text2SIP bridge
# Role: SIP client -> local Mosquitto -> Bridge -> T2S Master
#
# Version: 2.3 (2025-11-17)
#
# Änderungen ggü. 2.2:
#  - corr vollständig entfernt (weder gesendet noch geprüft)
#  - erster valide Response auf Response-Topic reicht
#  - File::Slurp entfernt, Standardschreibzugang für health.json
#  - Stabilität: 3 Versuche, lokaler Broker, Subscriber vor Publisher
#
# Exit codes:
#   0 = OK (response received)
#   1 = Error (no response after retries / connect error)
# =============================================================================

use strict;
use warnings;
use utf8;
use open ':std', ':utf8';

use LoxBerry::System;
use LoxBerry::IO;
use JSON qw(encode_json decode_json);
use Sys::Hostname qw(hostname);
use POSIX qw(strftime);
use Getopt::Long qw(GetOptions);
use Time::HiRes qw(time sleep);
use File::Path qw(make_path);

# =============================================================================
# 0. Optionaler Random-Delay um mehrere Bridges zu entkoppeln
# =============================================================================
my $rand_delay = rand(9.5) + 0.5;   # 0.5–10 Sekunden
sleep($rand_delay);

# =============================================================================
# 1. Optionen
# =============================================================================
my $quiet = 0;
GetOptions("quiet" => \$quiet);

# =============================================================================
# 2. Pfade / Dateien
# =============================================================================
my $CFG_FILE    = "REPLACELBHOMEDIR/config/plugins/text2sip/Text2SIP.cfg";

my $ramdir      = '/run/shm/text2sip';
my $stdlogdir   = 'REPLACELBHOMEDIR/log/plugins/text2sip';
my $LOGFILE     = "$ramdir/handshake_test.log";
my $healthfile  = "$ramdir/health.json";
my $ROLE_MARKER = '/etc/mosquitto/role/sip-bridge';

# =============================================================================
# 3. Sicherstellen: RAM-Verzeichnis + Symlinks
# =============================================================================
if ( ! -d $ramdir ) {
    make_path($ramdir, { mode => 0775 });
    system("chown loxberry:loxberry '$ramdir' >/dev/null 2>&1");
}

# Symlinks ins Standard-Logverzeichnis anlegen
my $stdlog_symlink    = "$stdlogdir/handshake_test.log";
my $stdhealth_symlink = "$stdlogdir/health.json";

if ( ! -d $stdlogdir ) {
    make_path($stdlogdir, { mode => 0775 });
    system("chown loxberry:loxberry '$stdlogdir' >/dev/null 2>&1");
}

if ( ! -e $stdlog_symlink ) {
    symlink $LOGFILE, $stdlog_symlink;
}
if ( ! -e $stdhealth_symlink ) {
    symlink $healthfile, $stdhealth_symlink;
}

# =============================================================================
# 4. Logging
# =============================================================================
sub log_msg {
    my ($level, $msg) = @_;
    my $ts = strftime "%Y-%m-%d %H:%M:%S", localtime;

    # Konsole (außer quiet & nicht-ERROR)
    print "[$ts] $level $msg\n" unless $quiet && $level ne '<ERROR>';

    # Datei
    if (open my $fh, '>>', $LOGFILE) {
        print $fh "[$ts] $level $msg\n";
        close $fh;
    }
}

log_msg("<INFO>", "===== mqtt_handshake_test.pl v2.3 started =====");

# =============================================================================
# 5. Wenn keine Bridge-Rolle vorhanden → nichts tun, sauber raus
# =============================================================================
if ( ! -e $ROLE_MARKER ) {
    log_msg("<INFO>", "No 'sip-bridge' role marker ($ROLE_MARKER) — exiting without handshake.");
    exit 0;
}

# =============================================================================
# 6. Client-ID bestimmen (Single Source: Text2SIP.cfg → BRIDGE_USER)
# =============================================================================
my $hostname = LoxBerry::System::lbhostname() || hostname() || 'unknown';

my $client_id;

if (-f $CFG_FILE) {
    eval {
        require Config::Simple;
        my $cfg = Config::Simple->new($CFG_FILE);
        my $cfg_user = $cfg->param('default.BRIDGE_USER');
        $client_id = $cfg_user if ($cfg_user && $cfg_user ne '');
        1;
    } or do {
        log_msg("<WARNING>", "Cannot read BRIDGE_USER from $CFG_FILE: $@");
    };
}

# Fallback, falls cfg leer: t2s-bridge-<hostname>
$client_id ||= "t2s-bridge-$hostname";

log_msg("<INFO>", "Effective BRIDGE_USER / client_id = $client_id");

# Topics
my $REQ_TOPIC  = "tts-handshake/request/$client_id";
my $RESP_TOPIC = "tts-handshake/response/$client_id";

# =============================================================================
# 7. MQTT-Creds: Lokaler Broker -> Bridge -> Master
# =============================================================================
my $cred = LoxBerry::IO::mqtt_connectiondetails();
my $host = $cred->{brokerhost} // '127.0.0.1';
my $port = $cred->{brokerport} // 1883;
my $user = $cred->{brokeruser} // '';
my $pass = $cred->{brokerpass} // '';

$ENV{MQTT_SIMPLE_ALLOW_INSECURE_LOGIN} = 1;

log_msg("<INFO>", "Using MQTT broker $host:$port (local -> bridge -> master)");
log_msg("<INFO>", "Request topic : $REQ_TOPIC");
log_msg("<INFO>", "Response topic: $RESP_TOPIC");

# =============================================================================
# 8. Net::MQTT::Simple laden (zur Laufzeit, mit Fehlerlog)
# =============================================================================
eval {
    require Net::MQTT::Simple;
    1;
} or do {
    log_msg("<ERROR>", "Net::MQTT::Simple not available: $@");
    exit 1;
};

# =============================================================================
# 9. Handshake-Funktion (Subscriber zuerst, dann Publish)
# =============================================================================
my $TIMEOUT_SEC       = 10;
my $PRE_SUB_DELAY     = 0.080;   # 80ms
my $POLL_INTERVAL_SEC = 0.050;   # 50ms

sub perform_handshake {
    my ($attempt, $host, $port, $user, $pass, $REQ_TOPIC, $RESP_TOPIC, $client_id, $hostname) = @_;

    my $server = "$host:$port";
    log_msg("<INFO>", "Attempt $attempt: Connecting to MQTT broker at $server ...");

    my $mqtt = eval { Net::MQTT::Simple->new($server) };
    if ($@ || !$mqtt) {
        log_msg("<WARNING>", "Attempt $attempt: Cannot connect to MQTT broker at $server: $@");
        return;
    }

    if ($user || $pass) {
        eval { $mqtt->login($user, $pass); };
        if ($@) {
            log_msg("<WARNING>", "Attempt $attempt: MQTT login failed for $user\@$server: $@");
            return;
        }
    }

    # Payload OHNE corr
    my $payload = encode_json({
        client   => $client_id,
        hostname => $hostname,
    });

    my $response;
    $mqtt->subscribe($RESP_TOPIC => sub {
        my ($topic, $message) = @_;

        my $data = eval { decode_json($message) };
        if ($@ || !$data || ref $data ne 'HASH') {
            log_msg("<WARNING>", "Attempt $attempt: Received invalid JSON on $topic");
            return;
        }

        # Optional: status check
        if (defined $data->{status} && $data->{status} ne 'ok') {
            log_msg("<WARNING>", "Attempt $attempt: Handshake status not OK on $topic");
            return;
        }

        $response = $data;
    });

    log_msg("<INFO>", "Attempt $attempt: Subscriber ready on $RESP_TOPIC");
    select undef, undef, undef, $PRE_SUB_DELAY;  # Race-Schutz

    # Anfrage senden
    log_msg("<INFO>", "Attempt $attempt: Sending handshake request to $REQ_TOPIC via $server");
    eval { $mqtt->publish($REQ_TOPIC, $payload); };
    if ($@) {
        log_msg("<WARNING>", "Attempt $attempt: Publish failed: $@");
        return;
    }

    # Auf Antwort warten
    my $start = time;
    while (time - $start < $TIMEOUT_SEC) {
        $mqtt->tick($POLL_INTERVAL_SEC);
        last if $response;
    }

    return $response;
}

# =============================================================================
# 10. Retry-Logik (max. 3 Versuche)
# =============================================================================
my $MAX_ATTEMPTS   = 3;
my $final_response;

for my $attempt (1 .. $MAX_ATTEMPTS) {

    my $resp = perform_handshake(
        $attempt,
        $host, $port, $user, $pass,
        $REQ_TOPIC, $RESP_TOPIC,
        $client_id, $hostname,
    );

    if ($resp) {
        $final_response = $resp;
        last;
    } else {
        if ($attempt < $MAX_ATTEMPTS) {
            log_msg("<WARNING>", "Attempt $attempt: No handshake response within ${TIMEOUT_SEC}s. Retrying …");
            sleep 1;
        } else {
            log_msg("<ERROR>", "Attempt $attempt: No handshake response within ${TIMEOUT_SEC}s. Giving up.");
        }
    }
}

# =============================================================================
# 11. Ergebnis + Health-File aktualisieren
# =============================================================================
if ($final_response) {

    my $srv      = $final_response->{server}    // 'unknown';
    my $iso_resp = $final_response->{iso_time}  // '';
    my $ts_resp  = $final_response->{timestamp} // '';

    log_msg("<OK>",   "Received handshake response from $srv (ts=$ts_resp iso=$iso_resp)");
    log_msg("<INFO>", "health.json for bridge on this host will be updated for [$client_id]");

    # ISO-Zeit für Health-File: 2025-11-17T06:53:00+01:00
    my $iso = strftime "%Y-%m-%dT%H:%M:%S%z", localtime;
    $iso =~ s/(\d{2})$/:$1/;  # +0100 -> +01:00

    my %health = (
        last_handshake => $iso,
        hostname       => $hostname,
        client         => $client_id,
        server         => $srv,
    );

    # health.json schreiben (ohne File::Slurp)
    eval {
        if (open my $fh, '>', $healthfile) {
            print $fh encode_json(\%health);
            close $fh;
        } else {
            die "Cannot open $healthfile for writing: $!";
        }

        my $uid = getpwnam('loxberry');
        my $gid = getgrnam('loxberry');
        chown $uid, $gid, $healthfile if defined $uid && defined $gid;
        chmod 0644, $healthfile;

        log_msg("<INFO>", "Updated health file: $healthfile");
        1;
    } or do {
        log_msg("<WARNING>", "Failed to write or chown/chmod health file: $@");
    };

    log_msg("<INFO>", "===== mqtt_handshake_test.pl finished OK =====");
    exit 0;

} else {
    log_msg("<ERROR>", "No handshake response after $MAX_ATTEMPTS attempts — exiting with error.");
    log_msg("<INFO>",  "===== mqtt_handshake_test.pl finished with ERROR =====");
    exit 1;
}
