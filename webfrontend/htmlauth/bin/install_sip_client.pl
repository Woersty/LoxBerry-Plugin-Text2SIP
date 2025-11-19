#!/usr/bin/env perl
# install_sip_client.pl — Install MQTT bridge config (Text2SIP) with role & conf handling
# RUN AS: loxberry (NOT root)
#
# Version: 1.5
# - Uses a single TLS cert/key pair for the bridge:
#       /etc/mosquitto/certs/sip-bridge/t2s-bridge.crt
#       /etc/mosquitto/certs/sip-bridge/t2s-bridge.key
#   (no client-specific cert filenames)
# - Client-specific topics for TTS:
#       topic tts-publish/<CLIENT_ID>/#   out 0
#       topic tts-subscribe/<CLIENT_ID>/# in 0
# - Handshake topics:
#       topic tts-handshake/request/#               out 0
#       topic tts-handshake/response/<CLIENT_ID>    in  0
#   → Request: local -> master (out)
#   → Response: master -> local (in)
# - No ACL handling (done on T2S master via AUTO-ACL + handshake listener)
#
# What it does:
#  - Abort if /etc/mosquitto/role/t2s-master exists
#  - Ensure /etc/mosquitto/conf.d/disabled exists
#  - Move LoxBerry defaults (mosq_mqttgateway.conf, mosq_passwd) to disabled/
#  - Install bridge certs & write 30-bridge-t2s.conf
#  - Ensure master hostname/IP in /etc/hosts (auto add/update)
#  - Restart Mosquitto via mqtt-handler.pl
#  - Optional handshake test
#
# Logs:
#   REPLACELBHOMEDIR/log/plugins/text2sip/client_install.log

use strict;
use warnings;
use utf8;
use open ':std', ':utf8';

use Getopt::Long qw(GetOptions);
use File::Temp qw(tempdir);
use File::Spec;
use File::Path qw(make_path);
use File::Basename;
use POSIX qw(strftime);
use File::Copy;
use Sys::Hostname qw(hostname);

# ---------- Logging ----------
my $logfile = 'REPLACELBHOMEDIR/log/plugins/text2sip/client_install.log';
open(my $logfh, '>>', $logfile) or die "Cannot open log file $logfile: $!";

sub _ts      { strftime "%Y-%m-%d %H:%M:%S", localtime }
sub log_line { my ($lvl,$msg)=@_; print $logfh "["._ts()."] $lvl $msg\n" }

sub LOGOK   { log_line("<OK>",      shift) }
sub LOGINF  { log_line("<INFO>",    shift) }
sub LOGWARN { log_line("<WARNING>", shift) }
sub LOGERR  { log_line("<ERROR>",   shift) }
sub LOGFAIL { log_line("<FAIL>",    shift) }

sub fatal {
    my ($msg) = @_;
    LOGERR($msg);
    close $logfh if defined fileno($logfh);
    exit 1;
}

LOGINF("==== Starting Text2SIP bridge client install v1.5 ====");

# ---------- Constants ----------
my $BUNDLE_DEFAULT = 'REPLACELBHOMEDIR/config/plugins/text2sip/bridge/t2s_bundle.tar.gz';

my $CA_DIR_SYS     = '/etc/mosquitto/ca';
my $CERTS_DIR_SYS  = '/etc/mosquitto/certs/sip-bridge';
my $CONF_DIR_SYS   = '/etc/mosquitto/conf.d';
my $DIS_DIR_SYS    = File::Spec->catdir($CONF_DIR_SYS, 'disabled');
my $ROLE_DIR       = '/etc/mosquitto/role';

my $MASTER_MARKER  = File::Spec->catfile($ROLE_DIR, 't2s-master');
my $BRIDGE_MARKER  = File::Spec->catfile($ROLE_DIR, 'sip-bridge');
my $BRIDGE_CONF    = File::Spec->catfile($CONF_DIR_SYS, '30-bridge-t2s.conf');

# Single cert/key name for all SIP bridges
my $CERT_BASENAME  = 't2s-bridge';

my ($CA_FILE_SYS, $CERT_FILE_SYS, $KEY_FILE_SYS);
my $CLIENT_ID      = 't2s-bridge';
my ($BRIDGE_HOST, $BRIDGE_PORT) = ('t2s.local', 8883);

my @LB_DEFAULT_CONFS = (
    File::Spec->catfile($CONF_DIR_SYS, 'mosq_mqttgateway.conf'),
    File::Spec->catfile($CONF_DIR_SYS, 'mosq_passwd'),
);

# ---------- CLI ----------
my $bundle     = $BUNDLE_DEFAULT;
my $no_restart = 0;
my $help       = 0;
my $NO_RENAME  = 0;
my $CLI_USER   = '';

GetOptions(
    'bundle|b=s'   => \$bundle,
    'no-rename!'   => \$NO_RENAME,
    'no-restart!'  => \$no_restart,
    'user|u=s'     => \$CLI_USER,
    'help|h!'      => \$help,
) or fatal("Invalid options. Use --help");

if ($help) {
    print <<"USAGE";
Usage: install_sip_client.pl [--bundle PATH] [--no-rename] [--no-restart] [--user CLIENT_ID]
  --bundle PATH   Path to t2s_bundle.tar.gz (default: $BUNDLE_DEFAULT)
  --no-rename     Skip bundle rename to *-installed-YYYY-MM-DD.tar.gz
  --no-restart    Skip Mosquitto restart at the end
  --user ID       Override CLIENT_ID from master.info (e.g. t2s-bridge-loxberry-dev)
  --help          Show this help
USAGE
    exit 0;
}

# ---------- Safety: must run as 'loxberry' (not root) ----------
if ($> == 0) {
    fatal("Run this script as 'loxberry', not root.");
}

# ---------- Roles ----------
if (-e $MASTER_MARKER) {
    fatal("Found role 't2s-master' – Bridge installation is not allowed on this host.");
}

system('sudo','install','-o','root','-g','root','-m','0755','-d', $ROLE_DIR) == 0
    or fatal("Cannot create role directory '$ROLE_DIR'");

if (! -e $BRIDGE_MARKER) {
    system('sudo','install','-o','root','-g','root','-m','0644','/dev/null', $BRIDGE_MARKER) == 0
        or fatal("Failed to create role marker '$BRIDGE_MARKER'");
    LOGOK("Created role marker '$BRIDGE_MARKER'.");
} else {
    LOGINF("Role marker '$BRIDGE_MARKER' already exists.");
}

# ---------- Bundle ----------
(-f $bundle && -r $bundle) or fatal("Cannot access bundle: $bundle");
LOGOK("Using bundle: $bundle");

my $tmpdir = tempdir('sip_bundle_XXXXXX', TMPDIR => 1, CLEANUP => 1);
system('tar', '-xzf', $bundle, '-C', $tmpdir) == 0 or fatal("Bundle extraction failed");

sub find_first {
    my ($root, $regex) = @_;
    my @todo = ($root);
    while (@todo) {
        my $d = shift @todo;
        opendir(my $dh, $d) or next;
        while (my $e = readdir($dh)) {
            next if $e =~ /^\.\.?$/;
            my $p = "$d/$e";
            push @todo, $p if -d $p;
            return $p if $p =~ $regex;
        }
        closedir $dh;
    }
    return undef;
}

my $ca_in  = find_first($tmpdir, qr{(?:^|/)mosq-ca\.crt$}i);
my $crt_in = find_first($tmpdir, qr{(?:^|/)(?!mosq-ca)[^/]+\.crt$}i);
my $key_in = find_first($tmpdir, qr/\.key$/);
my $acl_in = find_first($tmpdir, qr/aclfile$/);
my $info   = find_first($tmpdir, qr/master\.info$/);

$ca_in && $crt_in && $key_in or fatal("Missing certificate or key file in bundle");
LOGOK("Found CA, client cert and key in bundle.");

# ---------- Parse master.info (HOST/PORT/CLIENT_ID fallback) ----------
if ($info) {
    eval {
        open my $fh, '<:encoding(UTF-8)', $info or die $!;
        my $txt = do { local $/; <$fh> };
        close $fh;
        $txt =~ s/^\s+|\s+$//g;

        if ($txt =~ /^\s*\{.*\}\s*$/s) {
            require JSON::PP;
            my $j = JSON::PP::decode_json($txt);
            $BRIDGE_HOST = $j->{HOST}        // $j->{MASTER_HOST} // $BRIDGE_HOST;
            $BRIDGE_PORT = $j->{PORT}        // 8883;
            $CLIENT_ID   = $j->{CLIENT_ID}   // $CLIENT_ID;
        } else {
            for my $line (split /\R/, $txt) {
                next if $line =~ /^\s*#/;
                if ($line =~ /^\s*HOST\s*[:=]\s*(\S+)/)        { $BRIDGE_HOST = $1 }
                if ($line =~ /^\s*MASTER_HOST\s*[:=]\s*(\S+)/) { $BRIDGE_HOST = $1 }
                if ($line =~ /^\s*PORT\s*[:=]\s*(\d+)/)        { $BRIDGE_PORT = $1 }
                if ($line =~ /^\s*CLIENT_ID\s*[:=]\s*(\S+)/)   { $CLIENT_ID   = $1 }
            }
        }
        1;
    } or LOGWARN("master.info parsing failed: $@");
}

# ---------- CLI --user overrides master.info CLIENT_ID ----------
if (defined $CLI_USER && $CLI_USER ne '') {
    $CLIENT_ID = $CLI_USER;
    LOGINF("Overriding CLIENT_ID from CLI: $CLIENT_ID");
}

LOGINF("Bridge target: $BRIDGE_HOST:$BRIDGE_PORT, clientid=$CLIENT_ID");

# ---------- Ensure /etc/hosts entry ----------
my $HOSTS_FILE = '/etc/hosts';
my $MASTER_IP;

if ($info) {
    eval {
        open my $fh, '<:encoding(UTF-8)', $info or die $!;
        my $txt = do { local $/; <$fh> };
        close $fh;

        if ($txt =~ /^\s*\{.*\}\s*$/s) {
            require JSON::PP;
            my $j = JSON::PP::decode_json($txt);
            $MASTER_IP = $j->{IP}       // $j->{MASTER_IP};
        } else {
            for my $line (split /\R/, $txt) {
                next if $line =~ /^\s*#/;
                if ($line =~ /^\s*IP\s*[:=]\s*(\S+)/)        { $MASTER_IP = $1 }
                if ($line =~ /^\s*MASTER_IP\s*[:=]\s*(\S+)/) { $MASTER_IP = $1 }
            }
        }
        1;
    } or LOGWARN("master.info IP parsing failed: $@");
}

if ($BRIDGE_HOST !~ /^\d{1,3}(?:\.\d{1,3}){3}$/) {
    my $existing_line = `grep -E "^[0-9.]+\\s+$BRIDGE_HOST(\\s|\$)" $HOSTS_FILE 2>/dev/null`;
    chomp($existing_line);

    if ($existing_line eq '' && $MASTER_IP) {
        LOGINF("Adding missing host entry: $BRIDGE_HOST → $MASTER_IP");
        my $cmd = "echo '$MASTER_IP\t$BRIDGE_HOST' | sudo tee -a $HOSTS_FILE >/dev/null";
        system($cmd) == 0
            ? LOGOK("Added '$BRIDGE_HOST' with IP $MASTER_IP to /etc/hosts")
            : LOGWARN("Failed to add $BRIDGE_HOST to /etc/hosts — check sudo permissions");

    } elsif ($existing_line ne '' && $MASTER_IP) {
        if ($existing_line !~ /^\Q$MASTER_IP\E\b/) {
            LOGWARN("Host entry for $BRIDGE_HOST exists but with different IP. Updating to $MASTER_IP...");
            my $cmd = "sudo sed -i.bak '/\\s$BRIDGE_HOST(\\s|\$)/d' $HOSTS_FILE && echo '$MASTER_IP\t$BRIDGE_HOST' | sudo tee -a $HOSTS_FILE >/dev/null";
            system($cmd) == 0
                ? LOGOK("Updated '$BRIDGE_HOST' entry in /etc/hosts to IP $MASTER_IP")
                : LOGWARN("Failed to update $BRIDGE_HOST entry — check sudo permissions");
        } else {
            LOGINF("$BRIDGE_HOST already mapped to correct IP ($MASTER_IP) — no change needed");
        }
    } elsif (!$MASTER_IP) {
        LOGWARN("Host $BRIDGE_HOST not resolvable and no IP provided in master.info");
    } else {
        LOGINF("$BRIDGE_HOST is resolvable — no /etc/hosts update needed");
    }
} else {
    LOGINF("Bridge host is already an IP ($BRIDGE_HOST) — skipping /etc/hosts entry");
}

# ---------- Key/Cert match check ----------
my $mod_cert = `openssl x509 -in '$crt_in' -noout -modulus 2>/dev/null | openssl md5 2>/dev/null`;
my $mod_key  = `openssl rsa  -in '$key_in' -noout -modulus 2>/dev/null | openssl md5 2>/dev/null`;
chomp($mod_cert); chomp($mod_key);
if ($mod_cert ne $mod_key) {
    fatal("Certificate and private key do NOT match!");
} else {
    LOGOK("Key and certificate match.");
}

# ---------- Install certs (single global bridge cert) ----------
system('sudo','install','-d','-o','root','-g','mosquitto','-m','0750',$CA_DIR_SYS,$CERTS_DIR_SYS) == 0
    or fatal("Creating cert dirs failed");

my $ca_target   = File::Spec->catfile($CA_DIR_SYS, 'mosq-ca.crt');
my $crt_target  = File::Spec->catfile($CERTS_DIR_SYS, "$CERT_BASENAME.crt");
my $key_target  = File::Spec->catfile($CERTS_DIR_SYS, "$CERT_BASENAME.key");

system('sudo','install','-o','root','-g','root','-m','0644', $ca_in,  $ca_target) == 0
    or fatal("Installing CA file failed");

system('sudo','install','-o','root','-g','mosquitto','-m','0640', $crt_in, $crt_target) == 0
    or fatal("Installing client cert failed");
system('sudo','install','-o','root','-g','mosquitto','-m','0640', $key_in, $key_target) == 0
    or fatal("Installing client key failed");
LOGOK("Certificate chain installed (using $CERT_BASENAME.[crt|key]).");

# ---------- Allow loxberry read access via ACL ----------
system('sudo','setfacl','-R','-m','u:loxberry:rX','/etc/mosquitto') == 0
    ? LOGOK("Granted read access for user loxberry via ACLs.")
    : LOGWARN("Failed to set ACLs for loxberry.");

system('sudo','setfacl','-R','-m','d:u:loxberry:rX','/etc/mosquitto') == 0
    ? LOGOK("Granted default ACLs for loxberry (auto for new files).")
    : LOGWARN("Failed to set default ACLs for loxberry.");

# ---------- Prepare conf.d ----------
system('sudo','install','-o','root','-g','root','-m','0755','-d', $CONF_DIR_SYS) == 0
    or fatal("Cannot ensure conf.d exists");
system('sudo','install','-o','root','-g','root','-m','0755','-d', $DIS_DIR_SYS) == 0
    or fatal("Cannot ensure conf.d/disabled exists");

for my $f (@LB_DEFAULT_CONFS) {
    next unless (-e $f or -l $f);
    my $base = File::Basename::basename($f);
    my $dst  = File::Spec->catfile($DIS_DIR_SYS, $base);
    LOGINF("Trying to move $base to disabled/ ...");
    my $rc = system('sudo','mv','-f',$f,$dst);
    if ($rc == 0) {
        LOGOK("Moved $base to disabled/ (will be inactive).");
    } else {
        LOGFAIL("Failed to move $base (rc=$rc) — check sudoers or permissions.");
    }
}

# ---------- Write bridge config ----------
# - TTS topics client-spezifisch
# - Handshake:
#       request/#  out 0  (local -> master)
#       response/<CLIENT_ID> in 0 (master -> local)
my $conf_txt = <<"CONF";
# Auto-generated by Text2SIP

# ---- Listener ----
listener 1883
allow_anonymous true

# ---- Bridge Config ----
connection t2s-sip-bridge
address $BRIDGE_HOST:$BRIDGE_PORT

clientid $CLIENT_ID
cleansession true
restart_timeout 2 30
try_private true

bridge_cafile    /etc/mosquitto/ca/mosq-ca.crt
bridge_certfile  /etc/mosquitto/certs/sip-bridge/$CERT_BASENAME.crt
bridge_keyfile   /etc/mosquitto/certs/sip-bridge/$CERT_BASENAME.key
bridge_insecure  false
tls_version      tlsv1.2

notifications    true
bridge_protocol_version mqttv311

# T2S SIP Bridge Mapping (client-specific)
topic tts-publish/$CLIENT_ID/# out 0
topic tts-subscribe/$CLIENT_ID/# in 0

# Handshake: generic Request -> Master  (AUTO-ACL)
topic tts-handshake/request/# out 0

# Handshake: client-specific Response <- Master
topic tts-handshake/response/$CLIENT_ID in 0
CONF

my $tmp_conf = File::Spec->catfile($tmpdir, '30-bridge-t2s.conf');
open my $cfh, '>:encoding(UTF-8)', $tmp_conf or fatal("Cannot write temp conf");
print $cfh $conf_txt;
close $cfh;

system('sudo','install','-o','root','-g','mosquitto','-m','0644', $tmp_conf, $BRIDGE_CONF) == 0
    or fatal("Bridge config install failed");
LOGOK("Bridge config installed: $BRIDGE_CONF");

# ---------- Optional aclfile check (only logging, no ACL manipulation) ----------
if (defined $acl_in && -r $acl_in) {
    eval {
        open my $afh, '<:encoding(UTF-8)', $acl_in or die $!;
        local $/; my $acltxt = <$afh>; close $afh;
        if ($acltxt =~ /user\s+$CLIENT_ID\b/) {
            LOGOK("aclfile contains client id '$CLIENT_ID' (bundle OK).");
        } else {
            LOGWARN("aclfile does not mention client id '$CLIENT_ID' (non-fatal, AUTO-ACL on master will handle it).");
        }
        1;
    } or LOGWARN("aclfile check failed: $@");
} else {
    LOGINF("No aclfile in bundle (ok).");
}

# ---------- Bundle rename ----------
unless ($NO_RENAME) {
    if (-w $BUNDLE_DEFAULT && $bundle eq $BUNDLE_DEFAULT) {
        my ($d,$m,$y) = (localtime)[3,4,5];
        $y += 1900; $m += 1;
        my $date = sprintf("%04d-%02d-%02d", $y, $m, $d);
        my $new = $BUNDLE_DEFAULT;
        $new =~ s/\.tar\.gz$/-installed-$date.tar.gz/;
        if (rename($BUNDLE_DEFAULT, $new)) {
            LOGOK("Bundle renamed to: $new");
        } else {
            LOGWARN("Failed to rename bundle: $!");
        }
    } else {
        LOGINF("Skipping bundle rename (different path or not writable).");
    }
} else {
    LOGINF("Skipping bundle rename due to --no-rename");
}

# ---------- Restart Mosquitto ----------
unless ($no_restart) {
    LOGINF("Restarting Mosquitto …");
    system('sudo REPLACELBHOMEDIR/sbin/mqtt-handler.pl action=restartgateway >/dev/null 2>&1 || true');
    LOGOK("Mosquitto restarted via mqtt-handler.pl.");
    LOGINF("Waiting 3 seconds for Mosquitto to become ready...");
    sleep 3;
} else {
    LOGINF("Skipping Mosquitto restart due to --no-restart");
}

# ---------- Post-install handshake test ----------
my $handshake_script = 'REPLACELBHOMEDIR/webfrontend/htmlauth/plugins/text2sip/bin/mqtt_handshake_test.pl';
if (-x $handshake_script) {
    LOGINF("Running MQTT handshake test after installation...");
    my $rc = system($handshake_script);
    if ($rc == 0) {
        LOGOK("MQTT handshake test successful.");
    } else {
        LOGWARN("MQTT handshake test did not receive a response. This may be normal if no remote T2S master is online yet. See REPLACELBHOMEDIR/log/plugins/text2sip/handshake_test.log");
    }
} else {
    LOGINF("Handshake test script not found or not executable: $handshake_script");
}

LOGOK("=== Bridge client install complete ===");
close $logfh;
exit 0;
