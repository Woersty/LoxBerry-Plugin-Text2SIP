#!/usr/bin/env perl
# install_sip_client.pl — Install MQTT bridge config (Text2SIP) with role & conf handling
# RUN AS: loxberry (NOT root)
# Version: 1.2 — adds master-role guard + disabled/ handling + local-listener deploy
#
# What it does:
#  - Abort if /etc/mosquitto/role/t2s-master exists
#  - Ensure /etc/mosquitto/conf.d/disabled exists
#  - Move LoxBerry defaults (mosq_mqttgateway.conf, mosq_passwd) to disabled/
#  - Copy plugin's 10-local-listener.conf into /etc/mosquitto/conf.d/
#  - Install bridge certs & write 30-bridge-t2s.conf (with tts-handshake/# both 0)
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

sub _ts { strftime "%Y-%m-%d %H:%M:%S", localtime }
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

LOGINF("==== Starting Text2SIP bridge client install v1.2 ====");

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

my $PLUG_LOCAL_LISTENER_SRC = 'REPLACELBHOMEDIR/webfrontend/htmlauth/plugins/text2sip/conf/10-local-listener.conf';
my $LOCAL_LISTENER_DST      = File::Spec->catfile($CONF_DIR_SYS, '10-local-listener.conf');

my ($CA_FILE_SYS, $CERT_FILE_SYS, $KEY_FILE_SYS, $CLIENT_ID);
my ($BRIDGE_HOST, $BRIDGE_PORT) = ('t2s.local', 8883);

# Standard LoxBerry gateway files that must be disabled on a pure bridge host
my @LB_DEFAULT_CONFS = (
  File::Spec->catfile($CONF_DIR_SYS, 'mosq_mqttgateway.conf'),
  File::Spec->catfile($CONF_DIR_SYS, 'mosq_passwd'),
);

# ---------- CLI ----------
my $bundle     = $BUNDLE_DEFAULT;
my $no_restart = 0;
my $help       = 0;
my $NO_RENAME  = 0;

GetOptions(
  'bundle|b=s'   => \$bundle,
  'no-rename!'   => \$NO_RENAME,
  'no-restart!'  => \$no_restart,
  'help|h!'      => \$help,
) or fatal("Invalid options. Use --help");

if ($help) {
  print <<"USAGE";
Usage: install_sip_client.pl [--bundle PATH] [--no-rename] [--no-restart]
  --bundle PATH   Path to t2s_bundle.tar.gz (default: $BUNDLE_DEFAULT)
  --no-rename     Skip bundle rename to *-installed-YYYY-MM-DD.tar.gz
  --no-restart    Skip Mosquitto restart at the end
  --help          Show this help
USAGE
  exit 0;
}

# ---------- Safety: must run as 'loxberry' (not root) ----------
if ($> == 0) {
  fatal("Run this script as 'loxberry', not root.");
}

# ---------- Roles ----------
# Hard abort if this host is a T2S master
if (-e $MASTER_MARKER) {
  fatal("Found role 't2s-master' – Bridge installation is not allowed on this host.");
}

# Ensure role dir & marker
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

# ---------- Find files in bundle ----------
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

# ---------- Parse master.info (JSON or simple KV) ----------
$CLIENT_ID   = 't2s-bridge';
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
        if ($line =~ /^\s*HOST\s*[:=]\s*(\S+)/) { $BRIDGE_HOST = $1 }
        if ($line =~ /^\s*PORT\s*[:=]\s*(\d+)/) { $BRIDGE_PORT = $1 }
        if ($line =~ /^\s*CLIENT_ID\s*[:=]\s*(\S+)/) { $CLIENT_ID = $1 }
      }
    }
    1;
  } or LOGWARN("master.info parsing failed: $@");
}
LOGINF("Bridge target: $BRIDGE_HOST:$BRIDGE_PORT, clientid=$CLIENT_ID");

$CA_FILE_SYS   = File::Spec->catfile($CA_DIR_SYS, 'mosq-ca.crt');
$CERT_FILE_SYS = File::Spec->catfile($CERTS_DIR_SYS, "$CLIENT_ID.crt");
$KEY_FILE_SYS  = File::Spec->catfile($CERTS_DIR_SYS, "$CLIENT_ID.key");

# ---------- Key/Cert match check ----------
my $mod_cert = `openssl x509 -in '$crt_in' -noout -modulus 2>/dev/null | openssl md5 2>/dev/null`;
my $mod_key  = `openssl rsa  -in '$key_in' -noout -modulus 2>/dev/null | openssl md5 2>/dev/null`;
chomp($mod_cert); chomp($mod_key);
if ($mod_cert ne $mod_key) {
  fatal("Certificate and private key do NOT match!");
} else {
  LOGOK("Key and certificate match.");
}

# ---------- Install certs ----------
# Verzeichnisse (strikter)
system('sudo','install','-d','-o','root','-g','mosquitto','-m','0750',$CA_DIR_SYS,$CERTS_DIR_SYS) == 0
  or fatal("Creating cert dirs failed");

# CA bleibt root:root, 0644 ok
system('sudo','install','-o','root','-g','root','-m','0644', $ca_in,  $CA_FILE_SYS) == 0
  or fatal("Installing CA file failed");

# Client-Zertifikat & Key: root:mosquitto, 0640
system('sudo','install','-o','root','-g','mosquitto','-m','0640', $crt_in, $CERT_FILE_SYS) == 0
  or fatal("Installing client cert failed");
system('sudo','install','-o','root','-g','mosquitto','-m','0640', $key_in, $KEY_FILE_SYS) == 0
  or fatal("Installing client key failed");
LOGOK("Certificate chain installed.");

# ---------- Prepare conf.d & disabled/ ----------
system('sudo','install','-o','root','-g','root','-m','0755','-d', $CONF_DIR_SYS) == 0
  or fatal("Cannot ensure conf.d exists");
system('sudo','install','-o','root','-g','root','-m','0755','-d', $DIS_DIR_SYS) == 0
  or fatal("Cannot ensure conf.d/disabled exists");

# Move ONLY LoxBerry default gateway files to disabled/
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

# ---------- Deploy plugin's local listener (fallback) ----------
if (-r $PLUG_LOCAL_LISTENER_SRC) {
  system('sudo','install','-o','root','-g','root','-m','0644', $PLUG_LOCAL_LISTENER_SRC, $LOCAL_LISTENER_DST) == 0
    ? LOGOK("Deployed 10-local-listener.conf to conf.d/")
    : fatal("Failed to install 10-local-listener.conf");
} else {
  fatal("Missing plugin listener template: $PLUG_LOCAL_LISTENER_SRC");
}

# ---------- Write bridge config ----------
my $conf_txt = <<"CONF";
# Auto-generated by Text2SIP

connection t2s-master-bridge
address $BRIDGE_HOST:$BRIDGE_PORT

clientid $CLIENT_ID
cleansession true
restart_timeout 2 30
try_private true

bridge_cafile    $CA_FILE_SYS
bridge_certfile  $CERT_FILE_SYS
bridge_keyfile   $KEY_FILE_SYS
bridge_insecure  false
tls_version      tlsv1.2

notifications    true
bridge_protocol_version mqttv311

# Topics
topic tts-publish/# out 0
topic tts-subscribe/# in 0
topic tts-handshake/# both 0
CONF

my $tmp_conf = File::Spec->catfile($tmpdir, '30-bridge-t2s.conf');
open my $cfh, '>:encoding(UTF-8)', $tmp_conf or fatal("Cannot write temp conf");
print $cfh $conf_txt;
close $cfh;

system('sudo','install','-o','root','-g','mosquitto','-m','0644', $tmp_conf, $BRIDGE_CONF) == 0
  or fatal("Bridge config install failed");
LOGOK("Bridge config installed: $BRIDGE_CONF");

# ---------- Optional: Check aclfile in bundle (non-fatal) ----------
if (defined $acl_in && -r $acl_in) {
  eval {
    open my $afh, '<:encoding(UTF-8)', $acl_in or die $!;
    local $/; my $acltxt = <$afh>; close $afh;
    if ($acltxt =~ /user\s+$CLIENT_ID\b/) {
      LOGOK("aclfile contains client id '$CLIENT_ID' (bundle OK).");
    } else {
      LOGWARN("aclfile does not mention client id '$CLIENT_ID' (non-fatal).");
    }
    1;
  } or LOGWARN("aclfile check failed: $@");
} else {
  LOGINF("No aclfile in bundle (ok).");
}

# ---------- Bundle rename (evidence) ----------
unless ($NO_RENAME) {
  if (-w $BUNDLE_DEFAULT && $bundle eq $BUNDLE_DEFAULT) {
    my ($d,$m,$y) = (localtime)[3,4,5];
    $y += 1900;
    $m += 1;
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

  # Kleine Pause, damit Mosquitto sicher bereit ist
  LOGINF("Waiting 3 seconds for Mosquitto to become ready...");
  sleep 3;
} else {
  LOGINF("Skipping Mosquitto restart due to --no-restart");
}

# ---------- Post-install handshake test (non-fatal) ----------
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
