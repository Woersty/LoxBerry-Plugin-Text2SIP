#!/usr/bin/env perl
# uninstall_sip_client_bridge.pl — Safe or forced removal of T2S SIP client bridge
# Version: 1.3 — adds automatic cleanup of /etc/hosts entry for the T2S master
# Detects T2S Master role and protects shared Mosquitto files automatically.
# Optionally --force for complete uninstall, even on Master systems.

use strict;
use warnings;
use File::Copy;
use File::Path qw(remove_tree);
use POSIX qw(strftime);
use File::Basename;
use Getopt::Long;

# ========= CLI options =========
my $force = 0;
my $help  = 0;

GetOptions(
    "force" => \$force,
    "help"  => \$help
);

if ($help) {
    print <<'USAGE';
uninstall_sip_client_bridge.pl — Remove Text2SIP MQTT bridge from Mosquitto

Usage:
  uninstall_sip_client_bridge.pl [--force] [--help]

Options:
  --force   Performs a *full* uninstall (removes all bridge and CA files)
            Use only if this system is *not* a T2S Master.
  --help    Show this help message and exit.

Behavior:
  - Without --force:  SAFE mode (keep CA on Master)
  - With --force:     FULL uninstall (remove everything)

Logfile:
  REPLACELBHOMEDIR/log/plugins/text2sip/client_install.log
USAGE
    exit 0;
}

# ========= Logging =========
my $logfile = 'REPLACELBHOMEDIR/log/plugins/text2sip/client_install.log';
open(my $logfh, '>>', $logfile) or die "Cannot open log file $logfile: $!";

sub log_msg {
    my ($level, $msg) = @_;
    my $ts = strftime "%Y-%m-%d %H:%M:%S", localtime;
    print $logfh "[$ts] $level $msg\n";
    print STDERR "[$ts] $level $msg\n";
}

sub log_ok   { log_msg("<OK>",   @_); }
sub log_info { log_msg("<INFO>", @_); }
sub log_warn { log_msg("<WARN>", @_); }
sub log_error { log_msg("<ERROR>", @_); exit 1; }

log_info("==== Starting uninstall of Text2SIP bridge client v1.3 ====");

# ========= Paths =========
my $conf_d_dir       = '/etc/mosquitto/conf.d';
my $conf_d_disabled  = '/etc/mosquitto/conf.d/disabled';
my $cert_folder      = '/etc/mosquitto/certs/sip-bridge';
my $ca_file          = '/etc/mosquitto/ca/mosq-ca.crt';
my $role_bridge      = '/etc/mosquitto/role/sip-bridge';
my $role_t2s_master  = '/etc/mosquitto/role/t2s-master';
my $mqtt_handler     = 'REPLACELBHOMEDIR/sbin/mqtt-handler.pl';
my $hosts_file       = '/etc/hosts';

# ========= Role detection =========
my $is_master = -e $role_t2s_master ? 1 : 0;
if ($is_master && !$force) {
    log_info("T2S Master role detected – activating SAFE mode (keep shared files).");
} elsif ($is_master && $force) {
    log_warn("T2S Master role detected but --force used → proceeding with FULL uninstall!");
} else {
    log_info("No T2S Master role detected – proceeding with " . ($force ? "FULL" : "SAFE") . " uninstall.");
}

# ========= Step 1a: Remove bridge config =========
my $bridge_conf = "$conf_d_dir/30-bridge-t2s.conf";
my $bridge_host;
if (-e $bridge_conf) {
    # Try to extract hostname from bridge conf before removing
    eval {
        open my $fh, '<', $bridge_conf or die $!;
        while (<$fh>) {
            if (/^\s*address\s+(\S+):\d+/) {
                $bridge_host = $1;
                last;
            }
        }
        close $fh;
    };
    unlink($bridge_conf)
        ? log_ok("Removed bridge config: $bridge_conf")
        : log_warn("Failed to remove $bridge_conf: $!");
} else {
    log_info("Bridge config not found: $bridge_conf");
}

# ========= Step 1b: Local listener config (obsolete) =========
# NOTE: Since v1.3 the local listener (1883) is part of 30-bridge-t2s.conf.
# The former 10-local-listener.conf is no longer used or deployed.
#
# my $local_listener_conf = "$conf_d_dir/10-local-listener.conf";
# if (-e $local_listener_conf) {
#     unlink($local_listener_conf)
#         ? log_ok("Removed legacy listener config: $local_listener_conf")
#         : log_warn("Failed to remove legacy $local_listener_conf: $!");
# } else {
#     log_info("Legacy local listener config not found (expected).");
# }


# ========= Step 2: Restore disabled configs =========
if (-d $conf_d_disabled) {
    opendir(my $dh, $conf_d_disabled) or log_error("Cannot open $conf_d_disabled: $!");
    while (my $file = readdir($dh)) {
        next if $file =~ /^\./;
        my $src = "$conf_d_disabled/$file";
        my $dst = "$conf_d_dir/$file";
        next if $file =~ /30-bridge-t2s\.conf/;
        if (-e $src) {
            move($src, $dst)
                or log_warn("Failed to move $src to $dst: $!");
            log_ok("Restored original config: $dst");
        }
    }
    closedir($dh);
    rmdir($conf_d_disabled)
        ? log_ok("Removed folder: $conf_d_disabled")
        : log_warn("Could not remove $conf_d_disabled (may not be empty)");
} else {
    log_info("No conf.d/disabled folder found.");
}

# ========= Step 3: Remove sip-bridge cert folder =========
if (-d $cert_folder) {
    remove_tree($cert_folder, { error => \my $err });
    if (@$err) {
        for my $diag (@$err) {
            my ($file, $message) = %$diag;
            log_warn("Failed to remove $file: $message");
        }
    } else {
        log_ok("Removed cert folder: $cert_folder");
    }
} else {
    log_info("Cert folder $cert_folder not found.");
}

# ========= Step 4: Remove CA file (only if not master OR forced) =========
if ($force || !$is_master) {
    if (-e $ca_file) {
        unlink($ca_file)
            ? log_ok("Removed CA file: $ca_file")
            : log_warn("Failed to remove CA file: $!");
    } else {
        log_info("CA file $ca_file not found.");
    }
} else {
    log_info("CA file retained (SAFE mode: Master role active).");
}

# ========= Step 5: Remove role marker =========
if (-e $role_bridge) {
    unlink($role_bridge)
        ? log_ok("Removed role marker: $role_bridge")
        : log_warn("Failed to remove $role_bridge: $!");
} else {
    log_info("Role marker not found: $role_bridge");
}

# ========= Step 6: Clean /etc/hosts entry =========
if ($bridge_host && $bridge_host !~ /^\d{1,3}(?:\.\d{1,3}){3}$/) {
    log_info("Checking /etc/hosts for bridge host '$bridge_host'...");
    my $exists = system("grep -qE '\\s$bridge_host(\\s|\$)' $hosts_file") == 0;
    if ($exists) {
        log_info("Removing $bridge_host from /etc/hosts ...");
        my $cmd = "sudo cp $hosts_file ${hosts_file}.bak-t2s && sudo sed -i '/\\s$bridge_host(\\s|\$)/d' $hosts_file";
        system($cmd) == 0
            ? log_ok("Removed '$bridge_host' entry from /etc/hosts (backup: ${hosts_file}.bak-t2s)")
            : log_warn("Failed to modify /etc/hosts — check sudo permissions");
    } else {
        log_info("$bridge_host not found in /etc/hosts — nothing to clean.");
    }
} else {
    log_info("No valid bridge hostname found for /etc/hosts cleanup.");
}

# ========= Step 7: Restart Mosquitto =========
log_info("Restarting Mosquitto via mqtt-handler.pl ...");
my $rc = system("$mqtt_handler action=restartgateway >/dev/null 2>&1");
if ($rc == 0) {
    sleep 2;
    my $pid = `pgrep -x mosquitto 2>/dev/null`;
    chomp($pid);
    if ($pid) {
        log_ok("Mosquitto restarted successfully (PID $pid).");
    } else {
        log_warn("Mosquitto restart command succeeded, but no running PID found.");
    }
} else {
    log_warn("Mosquitto restart failed with exit code $rc.");
}

# ========= Finish =========
log_ok("Uninstall completed. (Master mode=$is_master, Force=$force)");
log_info("==== Finished uninstall ====");
close($logfh);
exit 0;
