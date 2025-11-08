#!/usr/bin/env perl
# mqtt_handshake_test.pl — Simple MQTT Handshake Test for T2S Master
# Author: LoxBerry Text2SIP Plugin
# Version: 1.3 (RAM logging in /run/shm/text2sip)
# -------------------------------------------------------------------
# - Publishes to: tts-handshake/request/<client>
# - Expects reply: tts-handshake/response/<client>
# -------------------------------------------------------------------
# Exit codes:
#   0 = OK (response received)
#   1 = Error (no response / connect/publish error)

use strict;
use warnings;
use utf8;
use open ':std', ':utf8';

use LoxBerry::System;
use LoxBerry::IO;
use Net::MQTT::Simple;
use JSON qw(encode_json decode_json);
use Sys::Hostname qw(hostname);
use POSIX qw(strftime);
use Getopt::Long qw(GetOptions);
use Time::HiRes qw(time);
use File::Path qw(make_path);

# ---------- Options ----------
my $quiet = 0;
GetOptions("quiet" => \$quiet);

# ---------- Config ----------
my $CLIENT_ID   = 't2s-bridge';
my $REQ_TOPIC   = "tts-handshake/request/$CLIENT_ID";
my $RESP_TOPIC  = "tts-handshake/response/$CLIENT_ID";
my $TIMEOUT_SEC = 10;

# ---------- Log- und Health-Dateien ----------
my $ramdir      = '/run/shm/text2sip';
my $stdlogdir   = '/opt/loxberry/log/plugins/text2sip';
my $LOGFILE     = "$ramdir/handshake_test.log";
my $healthfile  = "$ramdir/health.json";
my $ROLE_MARKER = '/etc/mosquitto/role/sip-bridge';

# Sicherstellen, dass RAM-Verzeichnis existiert
if ( ! -d $ramdir ) {
    make_path($ramdir, { mode => 0775 });
    system("chown loxberry:loxberry $ramdir");
}

# Symlinks ins Standard-Logverzeichnis anlegen (wenn nicht vorhanden)
my $stdlog_symlink  = "$stdlogdir/handshake_test.log";
my $stdhealth_symlink = "$stdlogdir/health.json";
if ( ! -e $stdlog_symlink ) {
    symlink $LOGFILE, $stdlog_symlink;
}
if ( ! -e $stdhealth_symlink ) {
    symlink $healthfile, $stdhealth_symlink;
}

# ----------- Wenn keine Bridge Installation vorhanden ist dann abbrechen -------------
if ( ! -e $ROLE_MARKER ) {
    exit 0;
}

# ---------- Logging ----------
sub log_msg {
    my ($level, $msg) = @_;
    my $ts = strftime "%Y-%m-%d %H:%M:%S", localtime;
    print "[$ts] $level $msg\n" unless $quiet && $level ne '<ERROR>';
    open my $fh, '>>', $LOGFILE;
    print $fh "[$ts] $level $msg\n";
    close $fh;
}

# ---------- LoxBerry MQTT Credentials ----------
my $cred = LoxBerry::IO::mqtt_connectiondetails();
my $host = $cred->{brokerhost} // '127.0.0.1';
my $port = $cred->{brokerport} // 1883;
my $user = $cred->{brokeruser} // '';
my $pass = $cred->{brokerpass} // '';

local $ENV{MQTT_SIMPLE_USERNAME} = $user if defined $user;
local $ENV{MQTT_SIMPLE_PASSWORD} = $pass if defined $pass;

# ---------- Prepare MQTT ----------
my $server = "$host:$port";
my $mqtt = eval { Net::MQTT::Simple->new($server) };
if ($@ || !$mqtt) {
    log_msg("<ERROR>", "Cannot connect to MQTT broker at $server: $@");
    exit 1;
}

# ---------- Handshake Test ----------
my $corr = int(time * 1000);
my $payload = encode_json({
    client    => $CLIENT_ID,
    timestamp => time,
    hostname  => hostname(),
    corr      => $corr,
});

my $response;
$mqtt->subscribe($RESP_TOPIC, sub {
    my ($topic, $msg) = @_;
    eval {
        my $data = decode_json($msg);
        if ($data->{corr} && $data->{corr} == $corr) {
            $response = $data;
        }
    };
});

# Publish handshake (ensures no cached retain)
eval {
    # Clear old retained message first (harmless if none)
    $mqtt->publish($REQ_TOPIC, "");

    # Add small random jitter to avoid identical payloads being cached
    my $json = encode_json({
        client    => $CLIENT_ID,
        timestamp => time,
        hostname  => hostname(),
        corr      => $corr,
        nonce     => int(rand(1000000))  # <- prevents payload caching
    });

    # Now send actual handshake
    $mqtt->publish($REQ_TOPIC, $json);
};


if ($@) {
    log_msg("<ERROR>", "Publish failed: $@");
    exit 1;
}

log_msg("<INFO>", "Sent handshake request to $REQ_TOPIC (corr=$corr) via $server");
my $start = time;
while (time - $start < $TIMEOUT_SEC) {
    $mqtt->tick(0.2);
    last if $response;
}
if ($response) {
    my $srv = $response->{server} // 'unknown';
    my $tsr = $response->{timestamp} // '';
    log_msg("<OK>", "Received handshake response from $srv at $tsr (corr=$corr)");

    # ---------- Health-File aktualisieren ----------
    my $timestamp  = strftime "%Y-%m-%d %H:%M:%S", localtime;

    eval {
        require JSON;
        require File::Slurp;

        my %health = ( last_handshake => $timestamp );
        File::Slurp::write_file($healthfile, JSON::encode_json(\%health));

        chown scalar(getpwnam('loxberry')), scalar(getgrnam('loxberry')), $healthfile;
        chmod 0644, $healthfile;

        log_msg("<INFO>", "Updated health file: $healthfile");
    };

    exit 0;
} else {
    log_msg("<ERROR>", "No handshake response within $TIMEOUT_SEC seconds (corr=$corr).");
    exit 1;
}
