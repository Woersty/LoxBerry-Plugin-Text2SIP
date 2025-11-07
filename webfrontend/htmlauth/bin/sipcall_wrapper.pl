#!/usr/bin/perl
use strict;
use warnings;

# =============================================================
# Text2SIP Wrapper v1.3 (2025-10-16)
# Purpose:
#   Ensures SIP calls bind to MASTER_IP and temporarily disables
#   docker0 if it exists. Keeps logging minimal and rotation-safe.
# =============================================================

my $VERSION = "v1.3 (2025-10-16)";
my $logfile = 'REPLACELBHOMEDIR/log/plugins/text2speech/Text2SIP.log';
my $binary  = 'REPLACELBHOMEDIR/webfrontend/htmlauth/plugins/text2sip/bin/sipcmd';

# --- Environment setup ---
my $valid_ip = $ENV{'MASTER_IP'} // '';   # <-- was HOST_IP
$ENV{'OPAL_INTERFACE'}     = $valid_ip;
$ENV{'OPAL_IFACE_EXCLUDE'} = join(',', grep { $_ } ($ENV{'OPAL_IFACE_EXCLUDE'}, 'docker0','172.16.0.0/12','172.17.0.0/16','172.17.0.1'));

if ($ENV{'OPAL_IFACE_EXCLUDE'}) {
    my %seen; my @u = grep { !$seen{$_}++ } split /,/, $ENV{'OPAL_IFACE_EXCLUDE'};
    $ENV{'OPAL_IFACE_EXCLUDE'} = join(',', @u);
}

# --- Header ---
print STDERR "[sipcall_wrapper] Starting Text2SIP Wrapper $VERSION\n";
print STDERR "[sipcall_wrapper] MASTER_IP=$valid_ip\n";
print STDERR "[sipcall_wrapper] OPAL_IFACE_EXCLUDE=$ENV{OPAL_IFACE_EXCLUDE}\n";  # (optional but useful)

# --- Check if docker0 exists and (if UP) bring it DOWN with sudo (+ temp remove addr) ---
my $SUDO = (-x '/usr/bin/sudo') ? '/usr/bin/sudo' : '/bin/sudo';
my $IP   = (-x '/sbin/ip')      ? '/sbin/ip'      : '/usr/sbin/ip';

my $docker_exists    = (system("$IP link show docker0 >/dev/null 2>&1") == 0) ? 1 : 0;
my $docker_was_up    = 0;   # <-- will mean admin-UP
my $docker_touched   = 0;
my $docker_ipcidr    = '';  # e.g. "172.17.0.1/16"
my $addr_removed     = 0;

if ($docker_exists) {
    my $line = qx{$IP -o link show docker0 2>/dev/null};  # contains flags + "state ..."

    # NEW: detect admin-UP via flags in <...>, not via "state UP"
    my ($flags) = ($line =~ /<([^>]*)>/);
    my $admin_up = ($flags && $flags =~ /\bUP\b/) ? 1 : 0;
    my $oper_up  = ($line =~ /\bstate\s+UP\b/i) ? 1 : 0;
    $docker_was_up = $admin_up;

    print STDERR "[sipcall_wrapper] docker0 flags=<" . ($flags // '') . "> oper_state_UP=$oper_up admin_UP=$admin_up\n";

    # current inet (if any)
    my $aline = qx{$IP -4 -o addr show dev docker0 2>/dev/null};
    if ($aline =~ /\binet\s+(\d+\.\d+\.\d+\.\d+\/\d+)/) {
        $docker_ipcidr = $1;
    }

    if ($docker_was_up) {
        print STDERR "[sipcall_wrapper] docker0 admin-UP → temporarily disabling\n";
        my $rc_down = system($SUDO, '-n', $IP, 'link', 'set', 'dev', 'docker0', 'down');
        if ($rc_down == 0) {
            $docker_touched = 1;
        } else {
            print STDERR "[sipcall_wrapper] ERROR: sudo/ip down failed (rc=$rc_down)\n";
        }
    } else {
        print STDERR "[sipcall_wrapper] docker0 admin-DOWN; not touching link state\n";
    }

    # Keep address removal (prevents 172.17.0.1 bind)
    if ($docker_ipcidr) {
        my $rc_del = system($SUDO, '-n', $IP, 'addr', 'del', $docker_ipcidr, 'dev', 'docker0');
        if ($rc_del == 0) {
            $addr_removed = 1;
            print STDERR "[sipcall_wrapper] Removed docker0 inet $docker_ipcidr (temporary)\n";
        } else {
            print STDERR "[sipcall_wrapper] WARN: could not remove docker0 inet $docker_ipcidr (rc=$rc_del)\n";
        }
    }
} else {
    print STDERR "[sipcall_wrapper] docker0 not present; skipping guard\n";
}

# --- Run the SIP command ---
print STDERR "[sipcall_wrapper] Executing: $binary @ARGV\n";
my $rc = system($binary, @ARGV);
my $exitcode = $rc >> 8;

# --- Restore docker0 only what we changed above ---
if ($addr_removed && $docker_ipcidr) {
    my $rc_add = system($SUDO, '-n', $IP, 'addr', 'add', $docker_ipcidr, 'dev', 'docker0');
    if ($rc_add == 0) {
        print STDERR "[sipcall_wrapper] Restored docker0 inet $docker_ipcidr\n";
    } else {
        print STDERR "[sipcall_wrapper] ERROR: restoring docker0 inet failed (rc=$rc_add)\n";
    }
}
if ($docker_touched) {
    print STDERR "[sipcall_wrapper] Restoring docker0 UP\n";
    my $rc_up = system($SUDO, '-n', $IP, 'link', 'set', 'dev', 'docker0', 'up');
    if ($rc_up != 0) {
        print STDERR "[sipcall_wrapper] ERROR: sudo/ip up failed (rc=$rc_up)\n";
    }
}

# --- After restore, verify and log (optional) ---
my $post = qx{$IP -o link show docker0 2>/dev/null};
my ($flags) = ($post =~ /<([^>]*)>/);
my $admin_up = ($flags && $flags =~ /\bUP\b/) ? 1 : 0;
my $has_addr = (qx{$IP -4 -o addr show dev docker0 2>/dev/null} =~ /\binet\s+\d+\.\d+\.\d+\.\d+\/\d+/) ? 1 : 0;
print STDERR sprintf "[sipcall_wrapper] Restore check: admin_UP=%d addr_restored=%d\n", $admin_up, $has_addr;

# --- Log call info to Text2SIP.log ---
my $logline = sprintf(
    "[sipcall_wrapper] MASTER_IP=%s  RC=%d  CMD=%s\n",
    $valid_ip, $exitcode, join(' ', @ARGV)
);
system("echo '$logline' >> $logfile 2>/dev/null");

print STDERR "[sipcall_wrapper] Finished (exit=$exitcode)\n";
exit($exitcode);
