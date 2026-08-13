#!/usr/bin/perl

# Copyright 2016 Christian Woerstenfeld, git@loxberry.woerstenfeld.de
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

##########################################################################
# Modules
##########################################################################

#!/usr/bin/perl

use strict;
use warnings;
use utf8;
binmode STDOUT, ":utf8";
no  strict 'refs';                           # nötig für ${$var}-Templateersetzung

# CGI / Fehlerausgabe
use CGI qw/:standard -utf8/;                 # header(), param(), …
use CGI::Carp qw(fatalsToBrowser);

# LoxBerry
use LoxBerry::System qw(is_enabled);
use LoxBerry::Log;
use LoxBerry::IO;

# Config / Dateisystem / Utils
use Config::Simple '-strict';
use Cwd 'abs_path';
use File::HomeDir;
use File::Temp;
use String::ShellQuote qw(shell_quote);
use File::Basename qw(dirname);
use File::Path qw(make_path);
use Fcntl qw(:flock);
use Fcntl qw(LOCK_EX LOCK_UN);
use Time::HiRes qw(gettimeofday);

# Protokolle / Formate
use JSON qw(decode_json encode_json);
use Net::MQTT::Simple;
use IO::Socket::INET;
use Encode qw(decode_utf8 encode_utf8);

# Plugin-Libs
use lib "$lbphtmlauthdir/lib";
use Text2SIP::Popup qw(flash_popup);
our @EXPORT_OK = qw(flash_popup confirm_popup);

##########################################################################
# Variables
##########################################################################

our ($cfg,$plugin_cfg,$phrase,$phraseplugin,$lang,$template_title,$helptext,
     $installfolder,$version,$do,$psubfolder,$CONTROL_PORT,$message,$req);
our ($pluginconfigdir,$pluginconfigfile,@language_strings,$languagefile,$languagefileplugin);
our ($namef,$value,%query);
our ($DEBUG_USE,$PLUGIN_USE,$MQTT_MODE,$MQTT_HOST,$MQTT_PORT,$MQTT_USERNAME,$MQTT_PASSWORD);
our ($logfile,$log);
our $HOST_IP        = LoxBerry::System::get_localip();
our $wgetbin;
our $POPUP   = '';
our $CONFIRM = '';
our $ffmpeg  = '/usr/bin/ffmpeg';

# T2S / MQTT
our ($T2S_INSTALLED,$T2S_USE,$T2SminVers,$t2s_is_installed);
our ($P2W_Text,$P2W_lang,$full_path_to_mp3,$mp3tmp,$ttsfile,$client);

# Pfade/Jobs/Audio
our ($pluginjobfile,$pluginwavfile,$plugintmpfile,$pluginbindir,$plugindatadir,$pico2wave,$cmd);

##########################################################################
# Setup / Einlesen
##########################################################################

$version        = "v2025.09.09";
$do             = "form";
$T2S_INSTALLED  = "false";
$T2S_USE        = "off";
$MQTT_MODE      = "local";
$MQTT_HOST      = "";
$MQTT_PORT      = "1883";
$MQTT_USERNAME  = "";
$MQTT_PASSWORD  = "";
$client         = "text2sip";
$logfile        = "Text2SIP.log";

my $home        = File::HomeDir->my_home;

##########################################################################
# Read Settings
##########################################################################

# In welchem Plugin-Subfolder liegen wir?
$psubfolder = abs_path($0);
$psubfolder =~ s{.*/(.+)/[^/]+$}{$1};

# LoxBerry system config lesen
$cfg           = Config::Simple->new("$home/config/system/general.cfg");
$installfolder = $cfg->param("BASE.INSTALLFOLDER");
$lang          = $cfg->param("BASE.LANG");
$wgetbin       = $cfg->param("BINARIES.WGET");

# Pluginconfig-Pfade
$pluginconfigdir  = "$home/config/plugins/$psubfolder";
$pluginconfigfile = "$pluginconfigdir/Text2SIP.cfg";

# Plugin-Dirs anlegen (falls nicht vorhanden)
make_path("$installfolder/log/plugins/$psubfolder")      unless -d "$installfolder/log/plugins/$psubfolder";
make_path("$installfolder/data/plugins/$psubfolder/wav") unless -d "$installfolder/data/plugins/$psubfolder/wav";
make_path("$installfolder/tmp/plugins/$psubfolder")      unless -d "$installfolder/tmp/plugins/$psubfolder";

# Binaries/Verzeichnisse
$pico2wave     = "/usr/bin/pico2wave";
$pluginbindir  = "$installfolder/webfrontend/htmlauth/plugins/$psubfolder/bin";
$plugindatadir = "$installfolder/data/plugins/$psubfolder/wav";
$plugintmpfile = "$installfolder/tmp/plugins/$psubfolder";

# Kodier-Helfer. Config::Simple, Backticks und die Kommandozeile arbeiten mit
# UTF-8-Bytes; CGI (-utf8) und die Sprachdateien liefern Zeichen. as_chars()
# wandelt beim Hereinkommen, as_bytes() beim Hinausgehen. Beide sind idempotent.
sub as_chars {
    my $v = shift;
    return '' unless defined $v;
    return $v if utf8::is_utf8($v);
    # Bestehende Konfigurationen koennen ISO-8859-1 enthalten, weil die
    # Einstellungsseite den Wert bisher unkodiert zurueckschrieb. Strikt als
    # UTF-8 versuchen, sonst als Latin-1 lesen statt Ersatzzeichen zu liefern.
    my $decoded = eval { Encode::decode('UTF-8', $v, Encode::FB_CROAK) };
    return defined $decoded ? $decoded : Encode::decode('ISO-8859-1', $v);
}

sub as_bytes {
    my $v = shift;
    return '' unless defined $v;
    return utf8::is_utf8($v) ? encode_utf8($v) : $v;
}

# MQTT 3.1.1 Hilfsfunktionen fuer die Validierung eines externen Brokers.
# Es wird ein echter CONNECT mit Host/IP, Port, Benutzername und Passwort
# ausgefuehrt und der CONNACK-Code des Brokers ausgewertet.
sub mqtt_encode_string {
    my ($value) = @_;
    $value = '' unless defined $value;
    my $bytes = as_bytes($value);
    return pack('n', length($bytes)) . $bytes;
}

sub mqtt_encode_remaining_length {
    my ($length) = @_;
    my $encoded = '';

    do {
        my $digit = $length % 128;
        $length = int($length / 128);
        $digit |= 0x80 if $length > 0;
        $encoded .= chr($digit);
    } while ($length > 0);

    return $encoded;
}

sub mqtt_connection_valid {
    my ($host, $port, $user, $pass) = @_;

    $host = '' unless defined $host;
    $user = '' unless defined $user;
    $pass = '' unless defined $pass;

    $host =~ s/^\s+//;
    $host =~ s/\s+$//;

    $port = 1883 unless defined $port && $port =~ /^\d+$/;
    $port = int($port);

    return 0 if $host eq '';
    return 0 if length($host) > 253;
    return 0 if $host =~ /\s/;
    return 0 if $port < 1 || $port > 65535;

    my $socket = IO::Socket::INET->new(
        PeerAddr => $host,
        PeerPort => $port,
        Proto    => 'tcp',
        Timeout  => 4,
    );
    return 0 unless $socket;

    $socket->autoflush(1);

    my $client_id = sprintf(
        'text2sip-validate-%d-%d',
        $$,
        int(rand(1_000_000))
    );

    # Variable Header: "MQTT", Protocol Level 4 (= MQTT 3.1.1)
    my $variable_header = mqtt_encode_string('MQTT') . chr(4);

    # CONNECT Flags: Clean Session always. Username/password only if supplied.
    my $connect_flags = 0x02;
    $connect_flags |= 0x80 if $user ne '';
    $connect_flags |= 0x40 if $pass ne '';

    $variable_header .= chr($connect_flags) . pack('n', 10);

    my $payload = mqtt_encode_string($client_id);
    $payload .= mqtt_encode_string($user) if $user ne '';
    $payload .= mqtt_encode_string($pass) if $pass ne '';

    my $remaining_length = length($variable_header) + length($payload);
    my $packet = chr(0x10) . mqtt_encode_remaining_length($remaining_length)
               . $variable_header . $payload;

    my $written = syswrite($socket, $packet);
    unless (defined $written && $written == length($packet)) {
        close $socket;
        return 0;
    }

    my $response = '';
    my $deadline = time() + 4;

    while (length($response) < 4 && time() <= $deadline) {
        my $buf = '';
        my $read = sysread($socket, $buf, 4 - length($response));
        last unless defined $read && $read > 0;
        $response .= $buf;
    }

    # MQTT 3.1.1 CONNACK: 0x20 0x02 <session-present> <return-code>
    my $ok = 0;
    if (length($response) >= 4) {
        my @b = unpack('C4', substr($response, 0, 4));
        $ok = 1 if $b[0] == 0x20 && $b[1] == 0x02 && $b[3] == 0x00;
    }

    # Graceful DISCONNECT if authentication/connection succeeded.
    if ($ok) {
        eval { syswrite($socket, chr(0xE0) . chr(0x00)); };
    }

    close $socket;
    return $ok;
}

# Temp-Dateinamen-Helfer
sub get_temp_filename {
    my ($suffix) = @_;
    my $fh = File::Temp->new(
        TEMPLATE => 'Text2SIP_XXXX',
        DIR      => $plugindatadir,
        SUFFIX   => $suffix
    );
    return $fh->filename;
}

$pluginjobfile = get_temp_filename('.job.tsp');
$pluginwavfile = get_temp_filename('_wav');
$plugintmpfile = get_temp_filename('.tmp.wav');

# Plugin-Config laden
$plugin_cfg    = Config::Simple->new($pluginconfigfile);

# --- Globales DEBUG_USE-Default aus Config ---
my $debug_raw  = eval { $plugin_cfg->param('default.DEBUG_USE') } // 'off';
$DEBUG_USE     = is_enabled($debug_raw) ? 'on' : 'off';

# sauber normalisieren: immer 'on' oder 'off'
if (!defined $DEBUG_USE || $DEBUG_USE ne 'on') {
    $DEBUG_USE = 'off';
}

my $pluginlogdir = "$installfolder/log/plugins/$psubfolder";
make_path($pluginlogdir) unless -d $pluginlogdir;

# WICHTIG: auch das LoxBerry-Logdir sicherstellen
if (defined $lbplogdir && $lbplogdir ne '') {
    make_path($lbplogdir) unless -d $lbplogdir;
}

$log = LoxBerry::Log->new ( 
	name => 'Text2SIP', 
	filename => '$lbplogdir', 
	append => 1
);

##########################################################################
# QUERY_STRING robust parsen -> %query
##########################################################################

%query = ();

if (defined $ENV{'QUERY_STRING'} && $ENV{'QUERY_STRING'} ne '') {
    foreach my $pair (split(/&/, $ENV{'QUERY_STRING'})) {

        my ($raw_name, $raw_value) = split(/=/, $pair, 2);

        # kein Name -> ignorieren
        next if not defined $raw_name or $raw_name eq '';

        # Undef in leeren String wandeln
        $raw_value //= '';

        # URL-Decoding für Namen
        $raw_name =~ tr/+/ /;
        $raw_name =~ s/%([a-fA-F0-9]{2})/pack("C", hex($1))/eg;

        # URL-Decoding für Wert
        $raw_value =~ tr/+/ /;
        $raw_value =~ s/%([a-fA-F0-9]{2})/pack("C", hex($1))/eg;

        $query{$raw_name} = $raw_value;
    }
}



# Set parameters coming in - get over post
  if ( !$query{'lang'} )         { if ( param('lang')         ) { $lang         = quotemeta(param('lang'));         } else { $lang         = $lang;  } } else { $lang         = quotemeta($query{'lang'});         }
  if ( !$query{'do'} )           { if ( param('do')           ) { $do           = quotemeta(param('do'));           } else { $do           = "form"; } } else { $do           = quotemeta($query{'do'});           }


# Init Language
# Clean up lang variable
  $lang         =~ tr/a-z//cd;
  $lang         = substr($lang,0,2);
  # If there's no language phrases file for choosed language, use english as default
  if (!-e "$installfolder/templates/plugins/$psubfolder/lang/language_$lang.dat")
  {
    $lang = "en";
  }
  
  # Read translations / phrases
  $languagefile       = "$installfolder/templates/system/$lang/language.dat";
  if (! -f $languagefile) {
	  $languagefile = "$installfolder/templates/system/en/language.dat";
  }
  $phrase             = new Config::Simple($languagefile);
  $languagefileplugin = "$installfolder/templates/plugins/$psubfolder/lang/language_$lang.dat";
  $phraseplugin       = new Config::Simple($languagefileplugin);
  foreach my $key (keys %{ $phraseplugin->vars() } )
  {
    (my $cfg_section,my $cfg_varname) = split(/\./,$key,2);
    push @language_strings, $cfg_varname;
  }
  use Encode qw(decode);
  foreach our $template_string (@language_strings)
  {
    ${$template_string} = decode('UTF-8', $phraseplugin->param($template_string));
  }
  
	#**************************************** Text2Speech plugin detection ************************************

	# (1) Detect if Text2Speech (T2S) plugin is installed
	$T2SminVers    = '1.6.0';        # optional version check

	my @plugins = LoxBerry::System::get_plugins();
	foreach my $plugin (@plugins) {
	    my $name  = lc($plugin->{PLUGINDB_NAME}  // '');
	    my $title = lc($plugin->{PLUGINDB_TITLE} // '');
	    if ($name eq 'text2speech' || $title eq 'text2speech') {
	        my $version = $plugin->{PLUGINDB_VERSION} // '';
	        if ($version ge $T2SminVers) {
	            $T2S_INSTALLED = "true";
	            last;
	        }
	    }
	}

	$t2s_is_installed = ($T2S_INSTALLED eq 'true') ? 1 : 0;
	
	# --- Tum Testen ---
	#$T2S_INSTALLED = "true";
	#************************************ End Text2Speech plugin detection ************************************

	  
##########################################################################
# Main program
##########################################################################

##########################################################################
# Main program
##########################################################################

if ($do eq "makecall")
{
    print header(-type => 'text/plain', -charset => 'UTF-8');
    my $guide = int($query{'vg'});

    $ENV{SDL_AUDIODRIVER} = 'dummy';  # verhindert ALSA-Init von ffplay/SDL

    # Optional: DEBUG_USE aus CGI überschreibt Config (z.B. TestSIP aus UI)
    my $debug_param = param('DEBUG_USE');
    if (defined $debug_param && $debug_param eq 'on') {
        $DEBUG_USE = 'on';
    }

    if ($guide == 0) {
        print($phraseplugin->param('TXT_JOB_QUEUED_INVALID_VGID'));
        print "\n<script> \$('#call_result".$guide."').removeClass( 'test2sip_job_ok' ).addClass( 'test2sip_job_failed' ); </script>\n";
        exit;
    }

    # ---------------------------------------------------------
    # Helper-Funktion – Config-Wert holen (neu + alt)
    # ---------------------------------------------------------
    my $cfg_get = sub {
        my ($key, $fallback) = @_;
        my $val;

        # Neuer Stil: [default] + default.KEY$guide
        eval { $val = $plugin_cfg->param("default.$key$guide"); };
        if (!defined $val || $val eq '') {
            # Alter Stil: KEY$guide
            eval { $val = $plugin_cfg->param("$key$guide"); };
        }
        $val = $fallback if (!defined $val || $val eq '');
        return $val;
    };

    # ---------------------------------------------------------
    # 1) Sprache + Text
    #    - Wenn CGI-Parameter vorhanden → verwenden (TestSIP)
    #    - sonst → aus Config lesen (Loxone / index.php)
    # ---------------------------------------------------------

    # Sprache
    $P2W_lang = param('P2W_lang'.$guide);
    if (!defined $P2W_lang || $P2W_lang eq '') {
        $P2W_lang = $cfg_get->('P2W_lang', 'de');
    }

    # Text
    my $raw_txt = param('P2W_Text'.$guide);
    if (!defined $raw_txt || $raw_txt eq '') {
        $raw_txt = $cfg_get->('P2W_Text', '');
    }
    $P2W_Text = defined $raw_txt ? $raw_txt : '';

    # Config und CGI liefern UTF-8-Bytes. Ab hier ist $P2W_Text ein Zeichen-String;
    # jede Ausgabe kodiert wieder nach UTF-8.
    $P2W_Text = as_chars($P2W_Text);

    # ---------------------------------------------------------
    # 2) SIP-Parameter – gleiche Logik (Param > Config)
    # ---------------------------------------------------------
    our $SIPCMD_CALLING_USER_NUMBER = param('SIPCMD_CALLING_USER_NUMBER'.$guide);
    if (!defined $SIPCMD_CALLING_USER_NUMBER || $SIPCMD_CALLING_USER_NUMBER eq '') {
        $SIPCMD_CALLING_USER_NUMBER = $cfg_get->('SIPCMD_CALLING_USER_NUMBER', '');
    }

    our $SIPCMD_CALLING_USER_PASSWORD = param('SIPCMD_CALLING_USER_PASSWORD'.$guide);
    if (!defined $SIPCMD_CALLING_USER_PASSWORD || $SIPCMD_CALLING_USER_PASSWORD eq '') {
        $SIPCMD_CALLING_USER_PASSWORD = $cfg_get->('SIPCMD_CALLING_USER_PASSWORD', '');
    }

    our $SIPCMD_CALLING_USER_NAME = param('SIPCMD_CALLING_USER_NAME'.$guide);
    if (!defined $SIPCMD_CALLING_USER_NAME || $SIPCMD_CALLING_USER_NAME eq '') {
        $SIPCMD_CALLING_USER_NAME = $cfg_get->('SIPCMD_CALLING_USER_NAME', '');
    }

    our $SIPCMD_SIP_PROXY = param('SIPCMD_SIP_PROXY'.$guide);
    if (!defined $SIPCMD_SIP_PROXY || $SIPCMD_SIP_PROXY eq '') {
        $SIPCMD_SIP_PROXY = $cfg_get->('SIPCMD_SIP_PROXY', '');
    }

    our $SIPCMD_CALLED_USER = param('SIPCMD_CALLED_USER'.$guide);
    if (!defined $SIPCMD_CALLED_USER || $SIPCMD_CALLED_USER eq '') {
        $SIPCMD_CALLED_USER = $cfg_get->('SIPCMD_CALLED_USER', '');
    }

    our $SIPCMD_CALL_PAUSE_BEFORE_GUIDE = param('SIPCMD_CALL_PAUSE_BEFORE_GUIDE'.$guide);
    if (!defined $SIPCMD_CALL_PAUSE_BEFORE_GUIDE || $SIPCMD_CALL_PAUSE_BEFORE_GUIDE eq '') {
        $SIPCMD_CALL_PAUSE_BEFORE_GUIDE = $cfg_get->('SIPCMD_CALL_PAUSE_BEFORE_GUIDE', 100);
    }
    $SIPCMD_CALL_PAUSE_BEFORE_GUIDE = int($SIPCMD_CALL_PAUSE_BEFORE_GUIDE);

    our $SIPCMD_CALL_PAUSE_AFTER_GUIDE = param('SIPCMD_CALL_PAUSE_AFTER_GUIDE'.$guide);
    if (!defined $SIPCMD_CALL_PAUSE_AFTER_GUIDE || $SIPCMD_CALL_PAUSE_AFTER_GUIDE eq '') {
        $SIPCMD_CALL_PAUSE_AFTER_GUIDE = $cfg_get->('SIPCMD_CALL_PAUSE_AFTER_GUIDE', 5000);
    }
    $SIPCMD_CALL_PAUSE_AFTER_GUIDE = int($SIPCMD_CALL_PAUSE_AFTER_GUIDE);

    our $SIPCMD_CALL_RESULT_VI = param('SIPCMD_CALL_RESULT_VI'.$guide);
    if (!defined $SIPCMD_CALL_RESULT_VI) {
        $SIPCMD_CALL_RESULT_VI = $cfg_get->('SIPCMD_CALL_RESULT_VI', '');
    }

    our $SIPCMD_CALL_TIMEOUT = param('SIPCMD_CALL_TIMEOUT'.$guide);
    if (!defined $SIPCMD_CALL_TIMEOUT || $SIPCMD_CALL_TIMEOUT eq '') {
        $SIPCMD_CALL_TIMEOUT = $cfg_get->('SIPCMD_CALL_TIMEOUT', 60);
    }
    $SIPCMD_CALL_TIMEOUT = int($SIPCMD_CALL_TIMEOUT);
    $SIPCMD_CALL_TIMEOUT = 60 if ($SIPCMD_CALL_TIMEOUT < 1);

    our $SIPCMD_MSINFO = param('SIPCMD_MSINFO'.$guide);
    if (!defined $SIPCMD_MSINFO) {
        $SIPCMD_MSINFO = $cfg_get->('SIPCMD_MSINFO', '');
    }

    our $SIPCMD_CONFIRMATION_DIGIT = param('SIPCMD_CONFIRMATION_DIGIT'.$guide);
    if (!defined $SIPCMD_CONFIRMATION_DIGIT || $SIPCMD_CONFIRMATION_DIGIT eq '') {
        $SIPCMD_CONFIRMATION_DIGIT = $cfg_get->('SIPCMD_CONFIRMATION_DIGIT', '-');
    }
    if ($SIPCMD_CONFIRMATION_DIGIT !~ /[0-9\*\#]/ ) {
        $SIPCMD_CONFIRMATION_DIGIT = "-";
    }

    # ---------------------------------------------------------
    # Sprache normalisieren
    # ---------------------------------------------------------
    my $unknown = "unbekannt";
    if    ($P2W_lang eq "gb" ) { $P2W_lang = "en-GB"; $unknown = "unknown" }
    elsif ($P2W_lang eq "us" ) { $P2W_lang = "en-US"; $unknown = "unknown" }
    elsif ($P2W_lang eq "es" ) { $P2W_lang = "es-ES"; $unknown = "desconocido" }
    elsif ($P2W_lang eq "fr" ) { $P2W_lang = "fr-FR"; $unknown = "inconnu" }
    elsif ($P2W_lang eq "it" ) { $P2W_lang = "it-IT"; $unknown = "sconosciuto" }
    elsif ($P2W_lang eq "de" ) { $P2W_lang = "de-DE"; $unknown = "unbekannt" }
    else {
        LOGERR "Error: Unknown language $P2W_lang - using german instead ";
        $P2W_lang = "de-DE";
    }

    # ----------------------------------------------------------
    # TTS-Parameter (&tts=...) aus QUERY_STRING
    # ----------------------------------------------------------
    my $tts_param = $query{'tts'} // '';
    $tts_param =~ s/\r?\n/ /g;
    $tts_param = as_chars($tts_param);

    # Merken, ob der ursprüngliche Text überhaupt ein "##" hatte
    my $had_placeholder = ($P2W_Text =~ /##/) ? 1 : 0;

    # ---------------------------------------------------------
    # MSINFO + &tts-Handling
    # Logik gemäß Doku + Fallback:
    # - Wenn keine MSINFO-URL → &tts ersetzt ## (falls vorhanden)
    # - Wenn MSINFO = "tts"   → &tts ersetzt ##
    # - Wenn MSINFO-URL, aber kein Wert → &tts ersetzt ## oder unknown
    # ---------------------------------------------------------
    if (defined $SIPCMD_MSINFO && $SIPCMD_MSINFO ne '') {

        if ($SIPCMD_MSINFO eq 'tts') {

            # Spezieller Modus: immer &tts für ##
            if ($P2W_Text =~ /##/) {
                if ($tts_param ne '') {
                    $P2W_Text =~ s/##/$tts_param/g;
                } else {
                    $P2W_Text =~ s/##/$unknown/g;
                }
            }

        } else {
            # Normale Miniserver-URL
            my $msinfo = `$wgetbin -a $lbplogdir/$logfile --retry-connrefused --tries=2 --waitretry=1 --timeout=1 --passive-ftp -nH -qO- "$SIPCMD_MSINFO" 2>&1 | grep value | cut -d'"' -f4`;
            chomp $msinfo;
            $msinfo = as_chars($msinfo);

            if ($? ne 0 || $msinfo eq '') {
                my $text = as_bytes($phraseplugin->param('ERROR0006')." ".$SIPCMD_MSINFO." ".$msinfo);
                system("echo '$text' >> $lbplogdir/$logfile");

                # Fallback: &tts oder unknown auf "##"
                if ($P2W_Text =~ /##/) {
                    if ($tts_param ne '') {
                        $P2W_Text =~ s/##/$tts_param/g;
                    } else {
                        $P2W_Text =~ s/##/$unknown/g;
                    }
                }
            } else {
                # Erfolgreich vom Miniserver gelesen -> MS-Wert ersetzt ##
                if ($P2W_Text =~ /##/) {
                    $P2W_Text =~ s/##/$msinfo/g;
                }
            }
        }

    } else {

        # Keine MSINFO-URL gesetzt → &tts darf direkt ## ersetzen
        if ($tts_param ne '' && $P2W_Text =~ /##/) {
            $P2W_Text =~ s/##/$tts_param/g;
        }
    }

    # ---------------------------------------------------------
    # Fallback: Kein "##" im Text, aber &tts/&tss wurde mitgegeben
    # → TTS-Text am Ende anhängen
    # ---------------------------------------------------------
    if ($tts_param ne '' && !$had_placeholder) {
        if ($P2W_Text ne '') {
            $P2W_Text .= ' ' . $tts_param;
        } else {
            $P2W_Text = $tts_param;
        }
    }

    # Zeilenumbrüche aus dem Text entfernen
    $P2W_Text =~ s/\r?\n/ /g;

    # Finalen Text loggen
    my $log_txt = as_bytes($P2W_Text);
    system("echo 'Final TTS text (VG=$guide): $log_txt' >> $lbplogdir/$logfile");

    # ---------------------------------------------------------
    # TTS-Routing + Anruf-Job
    # ---------------------------------------------------------

    $cmd = 'echo "################################ Start job from '.$pluginjobfile.' @ '.localtime(time).' " 2>&1 >>'.$lbplogdir."/".$logfile;
    system ("echo '".$cmd."' >> $pluginjobfile");

    #**************************** TTS routing (CONFIG-ONLY) ****************************
    my $cfg_flag = eval { $plugin_cfg->param('default.T2S_USE') } // 'off';
    $cfg_flag = lc($cfg_flag // 'off'); $cfg_flag =~ s/^\s+|\s+$//g;

    our $TTS_PREP_WRITTEN = 0;
    if (!$TTS_PREP_WRITTEN) {
        $TTS_PREP_WRITTEN = 1;
        system('echo "################################ Start TTS Preparation ################################" >> ' .
               $lbplogdir . '/' . $logfile);
    }

    my $ts_now = _ts();
    system('echo "'.$ts_now.' ## T2S_USE (config): ' . $cfg_flag . '" >> ' . $lbplogdir . '/' . $logfile);
    system('echo "'.$ts_now.' ## ROUTE: about to call t2svoice()" >> ' . $lbplogdir . '/' . $logfile) if $cfg_flag eq 'on';

    if ($cfg_flag eq 'on') {
        our $t2s_suppress_fallback = 0;   # Standard = kein Suppress
        &t2svoice();   # T2S via internal or external MQTT broker

        if ( !$t2s_suppress_fallback && ( !-e $pluginwavfile || -s $pluginwavfile <= 0 ) ) {
            system('echo "## ROUTE: t2svoice produced no WAV -> fallback to Pico" >> ' . $lbplogdir . '/' . $logfile);
            &usepico();
        }
    } else {
        &usepico();    # Pico
    }

    #************************** End TTS routing (CONFIG-ONLY) ***************************

    if ( $SIPCMD_CALL_TIMEOUT < 1 ) { $SIPCMD_CALL_TIMEOUT = 60 };

    # (Frueherer docker0/OPAL_IFACE_EXCLUDE-Hack entfaellt: pjsua bindet direkt
    #  per --bound-addr an $HOST_IP, waehlt also nie eine Docker-Bridge-IP.)
    # ---------------------------------------------------------------
    # pjsua-Anrufschicht (ersetzt sipcmd + sipcall_wrapper.pl).
    # --bound-addr bindet an die LAN-IP -> kein docker0/OPAL-Hack noetig.
    # Die WAV ($pluginwavfile) hat die gewaehlte TTS-Engine (pico2wave oder
    # Text2Speech-Plugin) bereits erzeugt; pjsua spielt sie NACH CONFIRMED
    # ab. DTMF-/Bestaetigungs-/Result-URL-Logik: pjsua_call.pl.
    # ---------------------------------------------------------------
    my $arch      = `dpkg --print-architecture 2>/dev/null`;
    chomp $arch;
    my $pjsua_bin = "$installfolder/data/plugins/$psubfolder/$arch/pjsua-$arch";
    my $driver    = "$pluginbindir/pjsua_call.pl";

    # Ohne passendes Binary kaeme der Anruf ohne erkennbaren Grund nicht zustande.
    if (! -e $pjsua_bin) {
        my $m = "## ERROR: no pjsua binary for architecture '$arch' (expected $pjsua_bin)";
        system('echo ' . shell_quote($m) . ' >> ' . shell_quote("$lbplogdir/$logfile"));
        print "\n<span class='test2sip_job_failed'>"
            . ($phraseplugin->param('TXT_JOB_QUEUED_FAIL') // 'Call failed')
            . "</span>\n<br/>pjsua: $arch\n";
        exit;
    }
    my $drv_debug = (defined $DEBUG_USE && $DEBUG_USE eq 'on') ? 1 : 0;
    my $disp      = defined $SIPCMD_CALLING_USER_NAME ? $SIPCMD_CALLING_USER_NAME : '';

    # Die TTS-Kette erzeugt zwei Dateien: eine echte RIFF/WAVE ($wav_path, .wav)
    # und ein headerloses RAW-s16le ($pluginwavfile, _wav) fuer sipcmds v-Kommando.
    # pjsua braucht die echte WAV -> aus dem _wav-Namen ableiten (siehe usepico/t2svoice).
    my $wav_for_pjsua = $pluginwavfile;
    $wav_for_pjsua =~ s/_wav$/.wav/i;
    $wav_for_pjsua = $pluginwavfile unless -e $wav_for_pjsua;  # Fallback (Diagnose im Log)

    # Argumente einzeln quoten. Das Passwort landet ausschliesslich im Jobfile
    # (fuer die Ausfuehrung noetig), NICHT im lesbaren Text2SIP.log.
    $cmd = join(' ',
        '/usr/bin/perl', shell_quote($driver),
        '--bin='           . shell_quote($pjsua_bin),
        '--bound='         . shell_quote($HOST_IP),
        '--proxy='         . shell_quote($SIPCMD_SIP_PROXY),
        '--user='          . shell_quote($SIPCMD_CALLING_USER_NUMBER),
        '--password='      . shell_quote($SIPCMD_CALLING_USER_PASSWORD),
        '--display='       . shell_quote($disp),
        '--called='        . shell_quote($SIPCMD_CALLED_USER),
        '--wav='           . shell_quote($wav_for_pjsua),
        '--pause_before='  . int($SIPCMD_CALL_PAUSE_BEFORE_GUIDE),
        '--pause_after='   . int($SIPCMD_CALL_PAUSE_AFTER_GUIDE),
        '--timeout='       . int($SIPCMD_CALL_TIMEOUT),
        '--confirm_digit=' . shell_quote($SIPCMD_CONFIRMATION_DIGIT),
        '--result_url='    . shell_quote($SIPCMD_CALL_RESULT_VI),
        '--log='           . shell_quote("$lbplogdir/$logfile"),
        '--debug='         . $drv_debug,
    );

    # Maskierte Kommandozeile ins lesbare Log (Passwort nie im Klartext).
    my $cmd_log = mask_secrets($cmd);
    $cmd_log =~ s/(--password=)\S+/${1}***/g;
    if (open my $lf, '>>:encoding(UTF-8)', "$lbplogdir/$logfile") {
        print $lf _ts() . " ## pjsua call: $cmd_log\n";
        close $lf;
    }

    # Jobfile per Perl-I/O schreiben (kein shell-echo wegen Quoting der Argumente).
    if (open my $jf, '>', $pluginjobfile) {
        my $qlog = shell_quote("$lbplogdir/$logfile");
        print $jf "#!/bin/bash\n";
        print $jf "echo \"################################ Start job from $pluginjobfile @ \$(date)\" >> $qlog\n";
        print $jf "chmod +x " . shell_quote($pjsua_bin) . " 2>/dev/null\n";
        print $jf $cmd . "\n";
        print $jf "rm -f " . shell_quote($pluginwavfile) . " " . shell_quote($wav_for_pjsua) . " " . shell_quote($plugintmpfile) . " 2>/dev/null\n";
        print $jf "echo \"################################ End job from $pluginjobfile\" >> $qlog\n";
        close $jf;
    } else {
        print "\n<br/>".$phraseplugin->param('TXT_JOB_QUEUED_FAIL');
        print "\n<script> \$('#call_result".$guide."').removeClass( 'test2sip_job_ok' ).addClass( 'test2sip_job_failed' ); </script>\n";
        exit;
    }

    # In die Task-Spooler-Queue stellen (CGI kehrt sofort zurueck; Anruf laeuft im Hintergrund).
    system ("echo -n 'Add job for guide ".$guide." to queue as #' 2>&1 >>$lbplogdir/$logfile");
    system("tsp bash $pluginjobfile >> $lbplogdir/$logfile 2>&1");
    if ( $? == 0 ) {
      print "\n<br/>".$phraseplugin->param('TXT_JOB_QUEUED_OK');
      print "\n<script> \$('#call_result".$guide."').removeClass( 'test2sip_job_failed' ).addClass( 'test2sip_job_ok' ); </script>\n";
    } else {
      print "\n<br/>".$phraseplugin->param('TXT_JOB_QUEUED_FAIL');
      print "\n<script> \$('#call_result".$guide."').removeClass( 'test2sip_job_ok' ).addClass( 'test2sip_job_failed' ); </script>\n";
    }
    exit;
}

  elsif ( $do eq "test")
  {
    print header(-type => 'text/plain', -charset => 'UTF-8');
    &test;
  }
  
  
#--------------- External MQTT endpoint validation ---------------
elsif ($do eq "check_mqtt_endpoint")
{
    print header(-type => 'application/json', -charset => 'UTF-8');

    my $host = param('MQTT_HOST') // '';
    my $port = param('MQTT_PORT') // '1883';
    my $user = param('MQTT_USERNAME') // '';
    my $pass = param('MQTT_PASSWORD') // '';

    $host =~ s/^\s+//;
    $host =~ s/\s+$//;

    $port =~ s/[^0-9]//g;
    $port = '1883' if $port eq '' || $port < 1 || $port > 65535;

    my $ok = mqtt_connection_valid($host, $port, $user, $pass) ? 1 : 0;
    print encode_json({ ok => $ok });
    exit;
}

#--------------- Configuration export ---------------
elsif ($do eq "config_export")
{
    our $pluginconfigfile;
    my @t = localtime();
    my $stamp = sprintf("%04d%02d%02d-%02d%02d%02d",
                        $t[5]+1900, $t[4]+1, $t[3], $t[2], $t[1], $t[0]);

    if (! -r $pluginconfigfile) {
        print header(-type => 'text/plain', -charset => 'UTF-8');
        print "configuration not readable\n";
        exit;
    }

    print header(-type => 'application/octet-stream', -charset => '',
                 -attachment    => "Text2SIP-config-$stamp.cfg",
                 -Content_Length => (-s $pluginconfigfile));
    binmode STDOUT;
    if (open(my $cf, '<', $pluginconfigfile)) { binmode $cf; print $_ while <$cf>; close $cf; }
    exit;
}

#--------------- Configuration import ---------------
elsif ($do eq "config_import")
{
    our $pluginconfigfile;
    print header(-type => 'application/json', -charset => 'UTF-8');

    # Die Datei wird als Bytes uebernommen und nicht dekodiert. Sie enthaelt
    # je nach Alter UTF-8 oder ISO-8859-1; as_chars() beim Lesen der Werte
    # erkennt beides, ein Dekodieren an dieser Stelle wuerde nur raten.
    my $payload = '';
    my $up = upload('cfgfile');
    if ($up) {
        binmode $up;
        local $/;
        $payload = <$up> // '';
    }
    $payload =~ s/\r\n/\n/g;

    if (length($payload) < 10 || length($payload) > 1048576) {
        print JSON::encode_json({ ok => 0, msg => 'unexpected file size' }); exit;
    }
    if ($payload =~ /[\x00-\x08\x0B\x0C\x0E-\x1F]/) {
        print JSON::encode_json({ ok => 0, msg => 'not a configuration file' }); exit;
    }
    # Eine brauchbare Konfiguration hat mindestens eine Zuweisung und den Plugin-Schalter.
    if ($payload !~ /^\s*[A-Za-z_][A-Za-z0-9_]*\s*=/m || $payload !~ /PLUGIN_USE/) {
        print JSON::encode_json({ ok => 0, msg => 'not a Text2SIP configuration' }); exit;
    }

    my @t = localtime();
    my $stamp = sprintf("%04d%02d%02d-%02d%02d%02d",
                        $t[5]+1900, $t[4]+1, $t[3], $t[2], $t[1], $t[0]);
    if (-e $pluginconfigfile) {
        require File::Copy;
        File::Copy::copy($pluginconfigfile, "$pluginconfigfile.$stamp.bak");
    }

    # Die Einstellungen werden zusammengefuehrt, nicht ersetzt. Eine mit einer
    # aelteren Version erzeugte Datei kennt spaeter hinzugekommene Einstellungen
    # nicht; die behalten ihren aktuellen Wert, statt zu verschwinden. Nicht mehr
    # verwendete Schluessel werden folgenlos mitgefuehrt, damit ein Import nie an
    # einem Versionsunterschied scheitert.
    my %imported;
    foreach my $line (split /\n/, $payload) {
        next if $line =~ /^\s*[;#]/;
        next if $line =~ /^\s*\[/;
        next unless $line =~ /^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$/;
        my ($k, $v) = ($1, $2);
        $v =~ s/^"(.*)"$/$1/s;
        $imported{$k} = $v;
    }

    if (!%imported) {
        print JSON::encode_json({ ok => 0, msg => 'no settings found in file' });
        exit;
    }

    my $target = eval { Config::Simple->new($pluginconfigfile) }
              || eval { Config::Simple->new(syntax => 'ini') };
    if (!$target) {
        print JSON::encode_json({ ok => 0, msg => 'cannot read current configuration' });
        exit;
    }

    my %before  = map { $_ => 1 } keys %{ $target->vars() || {} };
    my $applied = 0;
    foreach my $k (sort keys %imported) {
        $target->param("default.$k", $imported{$k});
        $applied++;
    }
    my $kept = scalar(grep { my $n = $_; $n =~ s/^default\.//; !exists $imported{$n} } keys %before);

    if (eval { $target->write($pluginconfigfile); 1 }) {
        print JSON::encode_json({ ok => 1, msg => 'imported',
                                  applied => $applied, kept => $kept });
    } else {
        print JSON::encode_json({ ok => 0, msg => 'cannot write configuration' });
    }
    exit;
}

  #--------------- Check config -----------------
  elsif ($do eq "check_config")
  {
    print header(-type => 'text/plain', -charset => 'UTF-8');
    our $output;
	#--------------- Save config -----------------
    if ( param('save_data') eq 1 )
    {
      $plugin_cfg = new Config::Simple(syntax=>'ini');
      $PLUGIN_USE = param('PLUGIN_USE');
		if ( $PLUGIN_USE ne "on" ) { $PLUGIN_USE = "off"; }

		$T2S_USE = param('T2S_USE');

		$DEBUG_USE = param('DEBUG_USE');
		if ( $DEBUG_USE ne "on" ) { $DEBUG_USE = "off"; }

		$MQTT_MODE = param('MQTT_MODE') // 'local';
		$MQTT_MODE = ($MQTT_MODE eq 'remote') ? 'remote' : 'local';
		$MQTT_HOST = param('MQTT_HOST') // '';
		$MQTT_HOST =~ s/^\s+//;
		$MQTT_HOST =~ s/\s+$//;
		$MQTT_PORT = param('MQTT_PORT') // '1883';
		$MQTT_PORT =~ s/[^0-9]//g;
		$MQTT_PORT = '1883' if $MQTT_PORT eq '' || $MQTT_PORT < 1 || $MQTT_PORT > 65535;
		$MQTT_USERNAME = param('MQTT_USERNAME') // '';
		$MQTT_PASSWORD = param('MQTT_PASSWORD') // '';

		# Bei aktivem Text2SIP + T2S und externem Broker darf nur gespeichert werden,
		# wenn der konfigurierte MQTT-Endpunkt vom LoxBerry aus erreichbar ist.
		if ($PLUGIN_USE eq 'on' && defined $T2S_USE && $T2S_USE eq 'on' && $MQTT_MODE eq 'remote') {
			unless (mqtt_connection_valid($MQTT_HOST, $MQTT_PORT, $MQTT_USERNAME, $MQTT_PASSWORD)) {
				print "__MQTT_CONNECTION_INVALID__";
				exit;
			}
		}
      our $LAST_ID                          = 0 + int(param('LAST_ID'));
      for (my $i=1; $i <= $LAST_ID; $i++)
      {
        if ( !param('P2W_lang'.$i) )
        {
          $plugin_cfg->delete('default.P2W_lang'.$i                      );
          $plugin_cfg->delete('default.P2W_Text'.$i                      );
          $plugin_cfg->delete('default.SIPCMD_CALLING_USER_NUMBER'.$i    );
          $plugin_cfg->delete('default.SIPCMD_CALLING_USER_PASSWORD'.$i  );
          $plugin_cfg->delete('default.SIPCMD_CALLING_USER_NAME'.$i      );
          $plugin_cfg->delete('default.SIPCMD_SIP_PROXY'.$i              );
          $plugin_cfg->delete('default.SIPCMD_CALLED_USER'.$i            );
          $plugin_cfg->delete('default.SIPCMD_CALL_PAUSE_BEFORE_GUIDE'.$i);
          $plugin_cfg->delete('default.SIPCMD_CALL_PAUSE_AFTER_GUIDE'.$i );
          $plugin_cfg->delete('default.SIPCMD_CALL_RESULT_VI'.$i );
          $plugin_cfg->delete('default.SIPCMD_CALL_TIMEOUT'.$i );
          $plugin_cfg->delete('default.SIPCMD_CONFIRMATION_DIGIT'.$i );
          $plugin_cfg->delete('default.SIPCMD_SIPCMD_MSINFO'.$i );
        }
        else
        { 
          $P2W_lang                       = "".param('P2W_lang'.$i                      );
          if ($P2W_lang ne "gb" && $P2W_lang ne "us" && $P2W_lang ne "es" && $P2W_lang ne "fr" &&  $P2W_lang ne "it" ) {$P2W_lang = "de"};
          $P2W_Text                       = "".param('P2W_Text'.$i                      );
          if ($P2W_Text eq "" ) 
          {
            print "\n<span class='test2sip_job_failed'>".$phraseplugin->param('TXT_SAVE_DIALOG_FAIL')."</span>\n<br/><br/>".$phraseplugin->param('TXT_SAVE_CFG_DIALOG_FAIL_PARAM_EMPTY')."<br/><span style='color:#0000FF; font-size: 16px; font-family:monospace;'>".substr($phraseplugin->param('TXT_P2W_Text'),0, -1)."</span><br/>".$phraseplugin->param('TXT_SAVE_CFG_DIALOG_FAIL_PARAM_VG')." <b><b>#$i</b></b>"; exit;
          }
          our $SIPCMD_CALLING_USER_NAME       = "".param('SIPCMD_CALLING_USER_NAME'.$i      );
          if ($SIPCMD_CALLING_USER_NAME eq "" ) 
          {
            print "\n<span class='test2sip_job_failed'>".$phraseplugin->param('TXT_SAVE_DIALOG_FAIL')."</span>\n<br/><br/>".$phraseplugin->param('TXT_SAVE_CFG_DIALOG_FAIL_PARAM_EMPTY')."<br/><span style='color:#0000FF; font-size: 16px; font-family:monospace;'>".$phraseplugin->param('TXT_SIPCMD_CALLING_USER_NAME')."</span><br/>".$phraseplugin->param('TXT_SAVE_CFG_DIALOG_FAIL_PARAM_VG')." <b>#$i</b>"; exit;
          }
          our $SIPCMD_CALLING_USER_NUMBER     = "".param('SIPCMD_CALLING_USER_NUMBER'.$i    );
          if ($SIPCMD_CALLING_USER_NUMBER eq "" ) 
          {
            print "\n<span class='test2sip_job_failed'>".$phraseplugin->param('TXT_SAVE_DIALOG_FAIL')."</span>\n<br/><br/>".$phraseplugin->param('TXT_SAVE_CFG_DIALOG_FAIL_PARAM_EMPTY')."<br/><span style='color:#0000FF; font-size: 16px; font-family:monospace;'>".$phraseplugin->param('TXT_SIPCMD_CALLING_USER_NUMBER')."</span><br/>".$phraseplugin->param('TXT_SAVE_CFG_DIALOG_FAIL_PARAM_VG')." <b>#$i</b>"; exit;
          }
          our $SIPCMD_CALLING_USER_PASSWORD   = "".param('SIPCMD_CALLING_USER_PASSWORD'.$i  );
          if ($SIPCMD_CALLING_USER_PASSWORD eq "" ) 
          {
            print "\n<span class='test2sip_job_failed'>".$phraseplugin->param('TXT_SAVE_DIALOG_FAIL')."</span>\n<br/><br/>".$phraseplugin->param('TXT_SAVE_CFG_DIALOG_FAIL_PARAM_EMPTY')."<br/><span style='color:#0000FF; font-size: 16px; font-family:monospace;'>".$phraseplugin->param('TXT_SIPCMD_CALLING_USER_PASSWORD')."</span><br/>".$phraseplugin->param('TXT_SAVE_CFG_DIALOG_FAIL_PARAM_VG')." <b>#$i</b>"; exit;
          }
          our $SIPCMD_SIP_PROXY               = "".param('SIPCMD_SIP_PROXY'.$i              );
          if ($SIPCMD_SIP_PROXY eq "" ) 
          {
            print "\n<span class='test2sip_job_failed'>".$phraseplugin->param('TXT_SAVE_DIALOG_FAIL')."</span>\n<br/><br/>".$phraseplugin->param('TXT_SAVE_CFG_DIALOG_FAIL_PARAM_EMPTY')."<br/><span style='color:#0000FF; font-size: 16px; font-family:monospace;'>".$phraseplugin->param('TXT_SIPCMD_SIP_PROXY')."</span><br/>".$phraseplugin->param('TXT_SAVE_CFG_DIALOG_FAIL_PARAM_VG')." <b>#$i</b>"; exit;
          }
          our $SIPCMD_CALLED_USER             = "".param('SIPCMD_CALLED_USER'.$i            );
          if ($SIPCMD_CALLED_USER eq "" ) 
          {
            print "\n<span class='test2sip_job_failed'>".$phraseplugin->param('TXT_SAVE_DIALOG_FAIL')."</span>\n<br/><br/>".$phraseplugin->param('TXT_SAVE_CFG_DIALOG_FAIL_PARAM_EMPTY')."<br/><span style='color:#0000FF; font-size: 16px; font-family:monospace;'>".substr($phraseplugin->param('TXT_SIPCMD_CALLED_USER'),0, -1)."</span><br/>".$phraseplugin->param('TXT_SAVE_CFG_DIALOG_FAIL_PARAM_VG')." <b>#$i</b>"; exit;
          }
          if (substr($SIPCMD_CALLED_USER,0,2) eq "00" || substr($SIPCMD_CALLED_USER,0,4) eq "0900" || substr($SIPCMD_CALLED_USER,0,4) eq "0190" || substr($SIPCMD_CALLED_USER,0,3) eq "010") 
          {
            print "\n<span class='test2sip_job_failed'>".$phraseplugin->param('TXT_SAVE_DIALOG_FAIL')."</span>\n<br/><br/>".$phraseplugin->param('TXT_SAVE_CFG_DIALOG_FAIL_NUMBER_BLOCKED')."<br/><span style='color:#0000FF; font-size: 16px; font-family:monospace;'>".$SIPCMD_CALLED_USER."</span><br/>".$phraseplugin->param('TXT_SAVE_CFG_DIALOG_FAIL_PARAM_VG')." <b>#$i</b>"; exit;
          }
          our $SIPCMD_CALL_PAUSE_BEFORE_GUIDE = int(param('SIPCMD_CALL_PAUSE_BEFORE_GUIDE'.$i));
          our $SIPCMD_CALL_PAUSE_AFTER_GUIDE  = int(param('SIPCMD_CALL_PAUSE_AFTER_GUIDE'.$i ));
          our $SIPCMD_CALL_RESULT_VI          = "".param('SIPCMD_CALL_RESULT_VI'.$i            );
          if ($SIPCMD_CALL_RESULT_VI ne "" && substr($SIPCMD_CALL_RESULT_VI,0,7) ne "http://") 
          {
            print "\n<span class='test2sip_job_failed'>".$phraseplugin->param('TXT_SAVE_DIALOG_FAIL')."</span>\n<br/><br/>".$phraseplugin->param('TXT_SAVE_CFG_DIALOG_FAIL_RESULT_PARAM_BAD')."<br/><span style='color:#0000FF; font-size: 16px; font-family:monospace;'>".substr($phraseplugin->param('TXT_SIPCMD_CALL_RESULT_VI'),0, -1)."</span><br/>".$phraseplugin->param('TXT_SAVE_CFG_DIALOG_FAIL_PARAM_VG')." <b>#$i</b>"; exit;
          }
          our $SIPCMD_CALL_TIMEOUT            = int(param('SIPCMD_CALL_TIMEOUT'.$i ));
          our $SIPCMD_MSINFO                  = param('SIPCMD_MSINFO'.$i );
          our $SIPCMD_CONFIRMATION_DIGIT      = param('SIPCMD_CONFIRMATION_DIGIT'.$i );
          if ($SIPCMD_CONFIRMATION_DIGIT =~ /[0-9\*\#]/ ) 
          {
          	$SIPCMD_CONFIRMATION_DIGIT = $SIPCMD_CONFIRMATION_DIGIT;
          }
          else
          {
          	$SIPCMD_CONFIRMATION_DIGIT = "-";
          };
          $plugin_cfg->param('default.P2W_lang'.$i                      ,"$P2W_lang"                       );
          $plugin_cfg->param('default.P2W_Text'.$i, as_bytes($P2W_Text));
          $plugin_cfg->param('default.SIPCMD_CALLING_USER_NUMBER'.$i    ,as_bytes($SIPCMD_CALLING_USER_NUMBER)     );
          $plugin_cfg->param('default.SIPCMD_CALLING_USER_PASSWORD'.$i  ,as_bytes($SIPCMD_CALLING_USER_PASSWORD)   );
          $plugin_cfg->param('default.SIPCMD_CALLING_USER_NAME'.$i      ,as_bytes($SIPCMD_CALLING_USER_NAME)       );
          $plugin_cfg->param('default.SIPCMD_SIP_PROXY'.$i              ,as_bytes($SIPCMD_SIP_PROXY)               );
          $plugin_cfg->param('default.SIPCMD_CALLED_USER'.$i            ,as_bytes($SIPCMD_CALLED_USER)             );
          $plugin_cfg->param('default.SIPCMD_CALL_PAUSE_BEFORE_GUIDE'.$i,"$SIPCMD_CALL_PAUSE_BEFORE_GUIDE" );
          $plugin_cfg->param('default.SIPCMD_CALL_PAUSE_AFTER_GUIDE'.$i ,"$SIPCMD_CALL_PAUSE_AFTER_GUIDE"  );
          $plugin_cfg->param('default.SIPCMD_CALL_RESULT_VI'.$i         ,as_bytes($SIPCMD_CALL_RESULT_VI)          );
          $plugin_cfg->param('default.SIPCMD_CALL_TIMEOUT'.$i           ,"$SIPCMD_CALL_TIMEOUT"            );
          $plugin_cfg->param('default.SIPCMD_CONFIRMATION_DIGIT'.$i     ,"$SIPCMD_CONFIRMATION_DIGIT"      );
          $plugin_cfg->param('default.SIPCMD_MSINFO'.$i                 ,as_bytes($SIPCMD_MSINFO)                  );
        }
      }
	  
	  $plugin_cfg->param('default.LAST_ID'    ,$LAST_ID    );
      $plugin_cfg->param('default.PLUGIN_USE' ,"$PLUGIN_USE" );
	  
	  $plugin_cfg->param('default.T2S_USE' ,"$T2S_USE" );
	  
      $plugin_cfg->param('default.MQTT_MODE'     ,"$MQTT_MODE" );
      $plugin_cfg->param('default.MQTT_HOST'     ,as_bytes($MQTT_HOST) );
      $plugin_cfg->param('default.MQTT_PORT'     ,"$MQTT_PORT" );
      $plugin_cfg->param('default.MQTT_USERNAME' ,as_bytes($MQTT_USERNAME) );
      $plugin_cfg->param('default.MQTT_PASSWORD' ,as_bytes($MQTT_PASSWORD) );

      $plugin_cfg->param('default.DEBUG_USE' ,"$DEBUG_USE" );
	  
	  my $version = LoxBerry::System::pluginversion();
	  $plugin_cfg->param('default.INSTALLED_VERSION', $version);
	  
	  
		if ( $plugin_cfg->write($pluginconfigfile) ) {
			print "\n<br/>" . $phraseplugin->param('TXT_SAVE_DIALOG_OK');
			print "\n<script> setTimeout( function() { location.reload(true); }, 1500); </script>\n";
			exit;
		} else {
			print "\n<br/><span class='test2sip_job_failed'>" .
				  $phraseplugin->param('TXT_SAVE_DIALOG_FAIL') .
				  "</span>\n";
			exit;
		}
	}
    else
    {
      print "\n<br/><span class='test2sip_job_failed'>".$phraseplugin->param('TXT_SAVE_DIALOG_FAIL')."</span>\n";
    }    
  }
  else
  {
    print "Content-Type: text/html; charset=UTF-8\n\n";
    &form;
  }
  exit;

#####################################################
#
# Subroutines
#
#####################################################

#####################################################
# Test-Sub to check if Text2SIP Control Server is up
#####################################################

  sub test
  {
      use IO::Socket::INET;
      # auto-flush on socket
      $| = 1;
      # create a connecting socket
      my $socket = new IO::Socket::INET (
      PeerHost => '0.0.0.0',
      PeerPort => "$CONTROL_PORT",
      Proto => 'tcp',
      );
      if ( $socket )
      {
        # data to send to a server
        $req = 'StAtUs_Text2SIP';
        my $size = $socket->send($req);

        # notify server that request has been sent
        shutdown($socket, 1);

        # receive a response of up to 1024 characters from server
        my $response = "";
        $socket->recv($response, 1024);
        $message = $response;

        $socket->close();
        print $response ;
      }
      else
      {
        print "Text2SIP_STATUS_DOWN" ;
      }
    exit;
  }
#####################################################
# Form-Sub
#####################################################

  sub form
  {
    # The page title read from language file + plugin name
    $template_title = $phrase->param("TXT0000") . ": " . $phraseplugin->param("MY_NAME");

    # Print Template header
    &lbheader;
	print $POPUP if $POPUP;
	print $CONFIRM if $CONFIRM;
	
    our $vg_select                      = "";
    our $P2W_lang                       = "de";
    our $vg_id                          = 0;
    our $LAST_ID                        = 0;
    our $PLUGIN_USE                     = "off";
	#********************** Added by OL ***********************************
	our $T2S_USE                     	= "off";
	#**********************************************************************
    our $MQTT_MODE                      = "local";
    our $MQTT_HOST                      = "";
    our $MQTT_PORT                      = "1883";
    our $MQTT_USERNAME                  = "";
    our $MQTT_PASSWORD                  = "";
    our $MQTT_HOST_HTML                 = "";
    our $MQTT_PORT_HTML                 = "1883";
    our $MQTT_USERNAME_HTML             = "";
    our $MQTT_PASSWORD_HTML             = "";
    our $DEBUG_USE                      = "off";
    our $P2W_Text                       = "";
    our $SIPCMD_CALLING_USER_NUMBER     = "";
    our $SIPCMD_CALLING_USER_PASSWORD   = "";
    our $SIPCMD_CALLING_USER_NAME       = "";
    our $SIPCMD_SIP_PROXY               = "";
    our $SIPCMD_CALLED_USER             = "";
    our $SIPCMD_CALL_PAUSE_BEFORE_GUIDE = 100;
    our $SIPCMD_CALL_PAUSE_AFTER_GUIDE  = 5000;
    our $SIPCMD_CALL_RESULT_VI          = "";
    our $SIPCMD_CALL_TIMEOUT            = 1;
    our $SIPCMD_CONFIRMATION_DIGIT      = "";
    our $SIPCMD_MSINFO                  = "";
	$T2S_INSTALLED					    =  $T2S_INSTALLED;
      if ( $plugin_cfg )
      {
        $LAST_ID                          =  $plugin_cfg->param('default.LAST_ID'                     );
        $PLUGIN_USE                       =  $plugin_cfg->param('default.PLUGIN_USE'                  );
		$T2S_USE = $plugin_cfg->param('default.T2S_USE');
        $MQTT_MODE                        =  $plugin_cfg->param('default.MQTT_MODE') // 'local';
        $MQTT_MODE                        =  ($MQTT_MODE eq 'remote') ? 'remote' : 'local';
        $MQTT_HOST                        =  as_chars($plugin_cfg->param('default.MQTT_HOST') // '');
        $MQTT_PORT                        =  $plugin_cfg->param('default.MQTT_PORT') // '1883';
        $MQTT_PORT                        =  '1883' if $MQTT_PORT !~ /^\d+$/ || $MQTT_PORT < 1 || $MQTT_PORT > 65535;
        $MQTT_USERNAME                    =  as_chars($plugin_cfg->param('default.MQTT_USERNAME') // '');
        $MQTT_PASSWORD                    =  as_chars($plugin_cfg->param('default.MQTT_PASSWORD') // '');
        $DEBUG_USE                        =  $plugin_cfg->param('default.DEBUG_USE'                   );
        for ($vg_id=1; $vg_id <= $LAST_ID; $vg_id++)
        {
          if ( $plugin_cfg->param('default.P2W_lang'.$vg_id) )
          {                                                                                                                       
            $P2W_lang                           =  "".$plugin_cfg->param('default.P2W_lang'.$vg_id                      );
            if ( "$P2W_lang" eq "" ) 
            {
               next; 
            }
            if ($P2W_lang ne "gb" && $P2W_lang ne "us" && $P2W_lang ne "es" && $P2W_lang ne "fr" &&  $P2W_lang ne "it" ) {$P2W_lang = "de"};
            $P2W_Text                       =  as_chars($plugin_cfg->param('default.P2W_Text'.$vg_id                          ));
            $SIPCMD_CALLING_USER_NUMBER     =  as_chars($plugin_cfg->param('default.SIPCMD_CALLING_USER_NUMBER'.$vg_id        ));
            $SIPCMD_CALLING_USER_PASSWORD   =  as_chars($plugin_cfg->param('default.SIPCMD_CALLING_USER_PASSWORD'.$vg_id      ));
            $SIPCMD_CALLING_USER_NAME       =  as_chars($plugin_cfg->param('default.SIPCMD_CALLING_USER_NAME'.$vg_id          ));
            $SIPCMD_SIP_PROXY               =  as_chars($plugin_cfg->param('default.SIPCMD_SIP_PROXY'.$vg_id                  ));
            $SIPCMD_CALLED_USER             =  as_chars($plugin_cfg->param('default.SIPCMD_CALLED_USER'.$vg_id                ));
            $SIPCMD_CALL_PAUSE_BEFORE_GUIDE =  int($plugin_cfg->param('default.SIPCMD_CALL_PAUSE_BEFORE_GUIDE'.$vg_id   ));
            $SIPCMD_CALL_PAUSE_AFTER_GUIDE  =  int($plugin_cfg->param('default.SIPCMD_CALL_PAUSE_AFTER_GUIDE'.$vg_id    ));
            $SIPCMD_CALL_RESULT_VI          =  as_chars($plugin_cfg->param('default.SIPCMD_CALL_RESULT_VI'.$vg_id             ));
            $SIPCMD_CALL_TIMEOUT            =  int($plugin_cfg->param('default.SIPCMD_CALL_TIMEOUT'.$vg_id              ));
            $SIPCMD_MSINFO                  =  as_chars($plugin_cfg->param('default.SIPCMD_MSINFO'.$vg_id                     ));
            $SIPCMD_CONFIRMATION_DIGIT      =  "".$plugin_cfg->param('default.SIPCMD_CONFIRMATION_DIGIT'.$vg_id         );
            if ($SIPCMD_CONFIRMATION_DIGIT =~ /[0-9\*\#]/ ) 
            {
            	$SIPCMD_CONFIRMATION_DIGIT = $SIPCMD_CONFIRMATION_DIGIT;
            }
            else
            {
            	$SIPCMD_CONFIRMATION_DIGIT = "-";
            };

            open(F,"$installfolder/templates/plugins/$psubfolder/guide_row.html") || die "Missing template /plugins/$psubfolder/guide_row.html";
            while (<F>)
            {
               $_ =~ s/<!--\$(.*?)-->/${$1}/g;
               $vg_select .= $_;
            }
            close(F);
          }
        }
      }
	  	  
	      # MQTT-Werte fuer HTML-Attribute separat escapen; Rohwerte bleiben fuer spaetere Runtime-Nutzung erhalten.
          $MQTT_HOST_HTML     = escapeHTML($MQTT_HOST // '');
          $MQTT_PORT_HTML     = escapeHTML($MQTT_PORT // '1883');
          $MQTT_USERNAME_HTML = escapeHTML($MQTT_USERNAME // '');
          $MQTT_PASSWORD_HTML = escapeHTML($MQTT_PASSWORD // '');

      # Parse the strings we want
      open(F,"$installfolder/templates/plugins/$psubfolder/settings.html") || die "Missing template plugins/$psubfolder/settings.html";
      while (<F>)
      {
        if ( $_ ne "" )
        {
          $_ =~ s/<!--\$(.*?)-->/${$1}/g;
        }
        print $_;
      }
      close(F);
	
    # Parse page footer
	&footer;
    exit;
  }
  
  

##########################################################################
# MQTT connection resolver for T2S
# - local  : use the MQTT broker configured by LoxBerry itself
# - remote : use host/port/credentials from Text2SIP.cfg
##########################################################################

sub get_t2s_mqtt_connection {
    our $plugin_cfg;

    my $mode = eval { $plugin_cfg->param('default.MQTT_MODE') } // 'local';
    $mode = lc(as_chars($mode));
    $mode =~ s/^\s+|\s+$//g;
    $mode = ($mode eq 'remote') ? 'remote' : 'local';

    if ($mode eq 'remote') {
        my $host = as_chars(eval { $plugin_cfg->param('default.MQTT_HOST') } // '');
        my $port = eval { $plugin_cfg->param('default.MQTT_PORT') } // '1883';
        my $user = as_chars(eval { $plugin_cfg->param('default.MQTT_USERNAME') } // '');
        my $pass = as_chars(eval { $plugin_cfg->param('default.MQTT_PASSWORD') } // '');

        $host =~ s/^\s+|\s+$//g;
        $user =~ s/^\s+|\s+$//g;
        $port = '1883' if !defined($port) || $port !~ /^\d+$/ || $port < 1 || $port > 65535;

        return {
            mode => 'remote',
            host => $host,
            port => int($port),
            user => $user,
            pass => $pass,
        };
    }

    my $cred = LoxBerry::IO::mqtt_connectiondetails();
    return {
        mode => 'local',
        host => $cred->{brokerhost} // '127.0.0.1',
        port => $cred->{brokerport} // 1883,
        user => $cred->{brokeruser} // '',
        pass => $cred->{brokerpass} // '',
    };
}


##########################################################################
# Use t2svoice for voice
##########################################################################

sub t2svoice {

    use Time::HiRes qw(time sleep);
    use JSON qw(decode_json encode_json);

    our ($P2W_Text, $lbplogdir, $logfile, $psubfolder);

    # ----------------------------------------------------------------------
    # Safe defaults for logging
    # ----------------------------------------------------------------------
    my $safe_logdir  = 'REPLACELBHOMEDIR/log/plugins/text2sip';
    my $safe_logfile = 'Text2SIP.log';

    $lbplogdir  = ($lbplogdir  && -d $lbplogdir)  ? $lbplogdir  : $safe_logdir;
    $logfile    = ($logfile    && $logfile ne '') ? $logfile    : $safe_logfile;
    $psubfolder = ($psubfolder && $psubfolder ne '') ? $psubfolder : 'text2sip';

    my $log_path     = "$lbplogdir/$logfile";
    my $RESP_TIMEOUT = 12;

    my $log = sub {
        my ($msg) = @_;
        if (open my $fh, '>>', $log_path) {
            print $fh _ts() . " $msg\n";
            close $fh;
        }
    };

    #$log->("################################ Start TTS Preparation ################################");

    # ----------------------------------------------------------------------
    # 1) Basic TTS parameters / sanity checks
    # ----------------------------------------------------------------------
    our $client;
    $client //= "text2sip";

    my $req_topic  = "tts-publish/$client";
    my $resp_topic = "tts-subscribe/$client";
    my ($corr_sec, $corr_usec) = gettimeofday();
    my $corr = sprintf("text2sip-%d-%06d-%d", $corr_sec, $corr_usec, $$);

    $log->("## Using client='$client'");
    $log->("## Request topic  = $req_topic");
    $log->("## Response topic = $resp_topic");
    $log->("## Correlation ID = $corr");

    # Ensure text exists, otherwise Pico fallback
    $P2W_Text //= '';
    $P2W_Text =~ s/\R//g;   # remove newlines

    if ($P2W_Text eq '') {
        $log->("## Empty TTS text – using Pico fallback");
        return usepico();
    }

    # ----------------------------------------------------------------------
    # 2) Build payload with per-request correlation ID
    # ----------------------------------------------------------------------
    my $payload_json = encode_json({
        text     => "$P2W_Text",
        nocache  => 1,
        logging  => 1,
        mp3files => 0,
        client   => $client,
        corr     => $corr,
        reply_to => $resp_topic,
    });

    $log->("## T2S payload prepared with corr='$corr'");

    # ----------------------------------------------------------------------
    # 3) Response parser with strict correlation matching
    # ----------------------------------------------------------------------
    my $parse_response = sub {
        my ($msg) = @_;

        my $d = eval { decode_json($msg) };
        if ($@ || !$d || ref $d ne 'HASH') {
            $log->("## ERROR: Invalid JSON in T2S response: $@");
            return undef;
        }

        my $r = $d->{response} // $d;

        my $response_corr = defined $r->{corr} ? "$r->{corr}" : '';
        if ($response_corr eq '' || $response_corr ne $corr) {
            $log->("## Ignoring T2S response with foreign/missing corr='$response_corr' (expected '$corr')");
            return undef;
        }

        # Master-level error
        if (defined $r->{status} && $r->{status} eq 'error') {
            my $err = $r->{message} // 'unknown error';
            $log->("## MQTT T2S returned ERROR: $err");
            our $t2s_abort_all = 1;
            return undef;
        }

        my $file = $r->{file};
        my $http = $r->{interfaces}->{httphostinterface} // $r->{httpinterface};

        if (!$file || !$http) {
            $log->("## ERROR: Incomplete T2S response (file/httpinterface missing)");
            return undef;
        }

        return {
            file          => $file,
            httpinterface => $http,
        };
    };

    # ----------------------------------------------------------------------
    # 4) Resolve MQTT broker and connect
    #    local  -> LoxBerry MQTT settings
    #    remote -> Text2SIP host/port/credentials
    # ----------------------------------------------------------------------
    my $mqtt_cfg = get_t2s_mqtt_connection();
    my $mqtt_mode = $mqtt_cfg->{mode} // 'local';
    my $host      = $mqtt_cfg->{host} // '';
    my $port      = $mqtt_cfg->{port} // 1883;
    my $user      = $mqtt_cfg->{user} // '';
    my $pass      = $mqtt_cfg->{pass} // '';

    if ($mqtt_mode eq 'remote') {
        if ($host eq '') {
            $log->("## ERROR: External MQTT broker selected but host is empty – using Pico fallback");
            return usepico();
        }
        $log->("## Using external MQTT broker $host:$port");
    } else {
        $log->("## Using internal LoxBerry MQTT broker $host:$port");
    }

    $ENV{MQTT_SIMPLE_ALLOW_INSECURE_LOGIN} = 1;

    my $mqtt;
    eval {
        $mqtt = Net::MQTT::Simple->new("$host:$port");
        $mqtt->login($user, $pass) if $user ne '' || $pass ne '';
        1;
    } or do {
        $log->("## MQTT connect/login failed for $mqtt_mode broker – using Pico fallback");
        return usepico();
    };

    if (!$mqtt) {
        $log->("## MQTT object not created – using Pico fallback");
        return usepico();
    }

    # ----------------------------------------------------------------------
    # 5) Subscribe to response topic
    # ----------------------------------------------------------------------
    my $reply;

    $mqtt->subscribe($resp_topic => sub {
        my ($t, $m) = @_;

        my $parsed = $parse_response->($m);

        # Hard abort from master error → NO EXIT → fallback!
        if (our $t2s_abort_all && $t2s_abort_all == 1) {
            $log->("## MQTT subscriber reported error – will fallback to Pico");
            return;
        }

        return unless $parsed;

        # Parser already verified that the response belongs to this request.
        $reply = $parsed;
    });

    # ----------------------------------------------------------------------
    # 6) Small delay to ensure subscription is active
    # ----------------------------------------------------------------------
    select undef, undef, undef, 0.080;  # 80 ms

    # ----------------------------------------------------------------------
    # 7) Publish T2S request
    # ----------------------------------------------------------------------
    $log->("## Publishing T2S request to $req_topic via $host:$port");
    $mqtt->publish($req_topic, $payload_json);

    # ----------------------------------------------------------------------
    # 8) Wait for the matching response (or timeout)
    # ----------------------------------------------------------------------
    my $end = time + $RESP_TIMEOUT;

    while (!$reply && time < $end) {

        # Master signaled error → break → fallback allowed
        if (our $t2s_abort_all && $t2s_abort_all == 1) {
            $log->("## MQTT subscriber reported error – stopping wait-loop");
            last;   # Kein exit!
        }

        $mqtt->tick();
        select undef, undef, undef, 0.05;
    }

    $mqtt->disconnect();

    # ----------------------------------------------------------------------
    # 9) Success → use TTS file
    # ----------------------------------------------------------------------
    if ($reply && $reply->{file} && $reply->{httpinterface}) {

        my $url = "$reply->{httpinterface}/$reply->{file}";
        $log->("## T2S MQTT OK: $url");

        our $full_path_to_mp3 = $url;
        return usetts();
    }

    # ----------------------------------------------------------------------
    # 10) Fallbacks (ALL POSSIBLE ERRORS)
    # ----------------------------------------------------------------------
    $log->("## No valid MQTT response – using Pico fallback");
    return usepico();
}


##########################################################################
# Use Pico for voice
##########################################################################

sub usepico
{
	my $sz_inB;
	my $sz_wavB;
	my $sz_rawB;
    # --- Log-Helpers ---
    my $log = sub {
        open my $fh, '>>', "$lbplogdir/$logfile";
        print $fh _ts(), " $_[0]\n";
        close $fh;
    };
	
    # <<< Änderung: $job schreibt direkt ins $logfile, NICHT ins Jobfile >>>
    my $job = sub {
		my ($msg) = @_;
		open my $fh, '>>', "$lbplogdir/$logfile" or return;
		print $fh _ts(), " $msg\n";
		close $fh;
	};

    # --- Binaries prüfen ---
	my $ff  = $ffmpeg    || '/usr/bin/ffmpeg';
	my $p2w = $pico2wave || '/usr/bin/pico2wave';
	if (!-x $p2w) { $log->("## ERROR: pico2wave not executable: $p2w"); return; }
	if (!-x $ff ) { $log->("## ERROR: ffmpeg not executable: $ff");   return; }

	# --- Rahmen-Infos loggen ---
	my $pre_ms = 100;                         # Vorlaufstille
	my $af     = "adelay=${pre_ms}|${pre_ms},volume=0.9";
	$log->("## usepico start lang=$P2W_lang pre_silence=${pre_ms}ms ffmpeg=$ff pico2wave=$p2w");
	$log->("## target base=$pluginwavfile tmp=$plugintmpfile");

	# UTF-8 für pico2wave absichern
	$ENV{LC_ALL} = 'C.UTF-8';
	$ENV{LANG}   = 'C.UTF-8';

	# --- 1) Pico: Text -> TMP-WAV ---
	$job->("## Generating voice (pico2wave)");
	my $text = as_bytes($P2W_Text);

	# stderr temporär ins Plugin-Log umleiten
	open my $SAVEDERR, ">&", \*STDERR;
	open STDERR, ">>", "$lbplogdir/$logfile";

	# WICHTIG: LIST-FORM (keine Shell, keine Expansion)
	my $rc_p2w = system($p2w, '-l', $P2W_lang, '-w', $plugintmpfile, $text);

	# stderr zurücksetzen
	open STDERR, ">&", $SAVEDERR; close $SAVEDERR;

	my $sz_in = (-e $plugintmpfile) ? (-s $plugintmpfile) : 0;
	my $exit  = ($rc_p2w >> 8);
	my $sig   = ($rc_p2w & 127);
	$log->("## pico2wave exit=$exit signal=$sig size=${sz_in}B -> $plugintmpfile");

	# Erfolg NUR über Größe bewerten (pico2wave kann trotz non-zero exit brauchbare WAV liefern)
	if ($sz_in < 128) {
		$log->("## ERROR: pico2wave output missing/too small (text_len=".length($text).")");
		return;
	}

    # --- 2) Ziele ableiten: .wav + _wav ---
    my ($wav_path, $raw_path);
    if    ($pluginwavfile =~ /_wav$/i){ ($wav_path=$pluginwavfile)=~s/_wav$/.wav/i; $raw_path=$pluginwavfile; }
    elsif ($pluginwavfile =~ /\.wav$/i){ $wav_path=$pluginwavfile; ($raw_path=$pluginwavfile)=~s/\.wav$/_wav/i; }
    else { $wav_path=$pluginwavfile.'.wav'; $raw_path=$pluginwavfile.'_wav'; }
    $log->("## targets wav=$wav_path raw=$raw_path");

    # --- 3) ffmpeg: TMP -> WAV (Header) ---
    unlink $wav_path;
    my $ff_wav = $ff
        .' -hide_banner -loglevel error -nostdin -y'
        .' -i "'.$plugintmpfile.'"'
        .' -filter:a "'.$af.'" -ac 1 -ar 8000 -acodec pcm_s16le -f wav'
        .' "'.$wav_path.'" 2>> '.$lbplogdir.'/'.$logfile;
    $job->("ffmpeg(wav): $ff_wav") if ($DEBUG_USE||'') eq 'on';

    my $rc1 = system($ff_wav);
    my $sz_wav = (-e $wav_path) ? (-s $wav_path) : 0;
    my $exit1 = $rc1 >> 8;
    $log->("## ffmpeg WAV rc=$rc1 exit=$exit1 size=$sz_wavB");

    if ($rc1 != 0 || $sz_wav <= 0) {
        $log->("## ERROR: ffmpeg WAV failed -> $wav_path");
        return;
    }

    # --- 4) ffmpeg: TMP -> RAW s16le (headerlos) ---
    unlink $raw_path;
    my $ff_raw = $ff
        .' -hide_banner -loglevel error -nostdin -y'
        .' -i "'.$plugintmpfile.'"'
        .' -filter:a "'.$af.'" -ac 1 -ar 8000 -acodec pcm_s16le -f s16le'
        .' "'.$raw_path.'" 2>> '.$lbplogdir.'/'.$logfile;
    $job->("ffmpeg(raw): $ff_raw") if ($DEBUG_USE||'') eq 'on';

    my $rc2 = system($ff_raw);
    my $sz_raw = (-e $raw_path) ? (-s $raw_path) : 0;
    my $exit2 = $rc2 >> 8;
    $log->("## ffmpeg RAW rc=$rc2 exit=$exit2 size=$sz_rawB");

    if ($rc2 != 0 || $sz_raw <= 0) {
        $log->("## ERROR: ffmpeg RAW failed -> $raw_path");
        return;
    }

    # --- 5) Plausibilitäts-Check Dauer & Größen ---
    # WAV: grob (44-Byte Header), PCM16 mono @8k => 16000 Bytes/s
    my $audio_bytes = $sz_wav > 44 ? ($sz_wav - 44) : $sz_wav;
    my $dur_wav = sprintf('%.2f', $audio_bytes / 16000.0);
    my $dur_raw = sprintf('%.2f', $sz_raw / 16000.0);
    my $delta   = sprintf('%.0f', abs($dur_wav - $dur_raw) * 1000);  # ms

    $log->("## DUR wav=${dur_wav}s raw=${dur_raw}s delta=${delta}ms");
    if (abs($dur_wav - $dur_raw) > 0.3) {
        $log->("## WARN: duration mismatch >300ms (prüfe Filter/Prepend)");
    }
    if ($dur_wav < 0.5) {
        $log->("## WARN: very short output (<0.5s) – Eingabetext/Engine prüfen");
    }

    # --- 6) Abschluss ---
    $log->("## usepico OK -> wav=$wav_path raw=$raw_path");
    $log->("## ROUTE: t2svoice completed");
	job_log_end();
}



##########################################################################
# Use T2S for voice
##########################################################################

sub usetts
{
    # --- Log-Helper (nur Text, kein 'echo ...') ---
    my $log = sub {
        open my $fh, '>>', "$lbplogdir/$logfile";
        print $fh _ts(), " $_[0]\n";
        close $fh;
    };

    # <<< Änderung: $job schreibt direkt ins $logfile, NICHT ins Jobfile >>>
    my $job = sub {
		my ($msg) = @_;
        open my $fh, '>>', "$lbplogdir/$logfile" or return;
        print $fh _ts(), " $msg\n";
        close $fh;
	};

    #$job->("## Generating voice by T2S Plugin");
    $log->("## Generating voice by T2S Plugin");

    # --- Sanity: Binaries vorhanden? ---
    my $ff = $ffmpeg || '/usr/bin/ffmpeg';
    if (!-x $ff) {
        $log->("## ERROR: Binary ffmpeg not found: $ff");
        &usepico; return;
    }

    # --- Sanity: Quelle vorhanden? ---
    if (!$full_path_to_mp3) {
        $log->("## ERROR: full_path_to_mp3 leer – fallback auf Pico");
        &usepico; return;
    }
    my $safe_mp3_url = mask_secrets($full_path_to_mp3);
    $log->("## MP3 URL: $safe_mp3_url");

    # --- Schritt 1: MP3 lokal herunterladen ---
    $mp3tmp = $plugintmpfile;  $mp3tmp =~ s/\.wav$/.mp3/;
    my $dl_cmd;
    if (-x '/usr/bin/curl') {
        $dl_cmd = sprintf('%s -fsSL -A %s -o %s %s 2>> %s',
            shell_quote('/usr/bin/curl'),
            shell_quote('Text2SIP/1.0'),
            shell_quote($mp3tmp),
            shell_quote($full_path_to_mp3),
            shell_quote("$lbplogdir/$logfile"));
    } elsif (-x '/usr/bin/wget') {
        $dl_cmd = sprintf('%s -q -L -U %s -O %s %s 2>> %s',
            shell_quote('/usr/bin/wget'),
            shell_quote('Text2SIP/1.0'),
            shell_quote($mp3tmp),
            shell_quote($full_path_to_mp3),
            shell_quote("$lbplogdir/$logfile"));
    } else {
        $log->("## ERROR: neither curl nor wget installed – fallback auf Pico");
        &usepico; return;
    }

    # >>> Maskiertes Download-Kommando ins Log
    my $log_dl_cmd = mask_secrets($dl_cmd);
    $job->("## Download: $log_dl_cmd");

    my $rc_dl = system($dl_cmd);
    my $sz_mp3 = (-e $mp3tmp) ? -s $mp3tmp : 0;
    $log->("## Download rc=$rc_dl size=${sz_mp3}B -> $mp3tmp");
    if ($rc_dl != 0 || $sz_mp3 < 128) {  # <128B: sehr wahrscheinlich leer/HTML
        $log->("## Download failed or file too small – fallback auf Pico");
        &usepico; return;
    }
    $job->("## Generated voice by T2S Plugin has been received");

    # --- Schritt 2: ffmpeg MP3 -> WAV (8kHz/mono/16bit) ---
    $job->("## Converting voice (ffmpeg)");
    my $ff_cmd = sprintf(
        '%s -hide_banner -loglevel error -y -i %s -filter:a %s -ac 1 -ar 8000 -acodec pcm_s16le -f wav %s 2>> %s',
        shell_quote($ff),
        shell_quote($mp3tmp),
        shell_quote('volume=0.9'),
        shell_quote($pluginwavfile),
        shell_quote("$lbplogdir/$logfile")
    );

    # >>> Maskiertes ffmpeg-Kommando ins Log
    my $log_ff_cmd = mask_secrets($ff_cmd);
    $job->("## ffmpeg: $log_ff_cmd");

    my $rc = system($ff_cmd);
    my $exit = $rc >> 8;
    my $sz_wav = (-e $pluginwavfile) ? -s $pluginwavfile : 0;

    # Grobe Dauer aus Bytes: (WAV-Header ~44B ignorieren)
    my $audio_bytes = $sz_wav > 44 ? ($sz_wav - 44) : $sz_wav;
    my $dur_wav = $audio_bytes > 0 ? sprintf('%.2f', $audio_bytes / 16000.0) : '0.00';

    if ($rc == 0 && $sz_wav > 0) {
        $log->('## ffmpeg ok '.$pluginwavfile.' size='.$sz_wav.'B dur='.$dur_wav.'s');
    } else {
        $log->('## ffmpeg failed (rc='.$rc.' exit='.$exit.') cmd='.$log_ff_cmd);
        &usepico;  # Fallback
        $log->("## ROUTE: t2svoice completed");
        job_log_end();
        return;
    }

    # --- Abschluss ---
    $job->("## Converting done");
    $log->("## ROUTE: t2svoice completed");
    job_log_end();
}

#####################################################
# Secret masking 
#####################################################

sub mask_secrets {
    my ($s) = @_;
    return $s unless defined $s;

    # JSON- / Key-Value-ähnliche Muster
    $s =~ s/("?(?:api[-_ ]?key|key|token|pass(?:word)?|secret|authorization)"?\s*[:=]\s*")([^"]+)(")/$1***$3/ig;
    $s =~ s/([?&](?:api[-_ ]?key|key|token|pass(?:word)?|secret)=)[^&]*/$1***/ig;
    $s =~ s/(\bBearer\s+)[A-Za-z0-9\.\-_]+/$1***/ig;

    # Basic-Auth in URL (user:pass@host)
    $s =~ s{(https?://[^:\s/]+:)[^@\s/]+(@)}{$1***$2}ig;

    return $s;
}

sub mask_hash {
    my ($h) = @_;
    return {} unless $h && ref $h eq 'HASH';
    my %c = %{$h};
    for my $k (keys %c) {
        if ($k =~ /pass|key|token|secret|authorization/i) {
            $c{$k} = '***';
        }
    }
    return \%c;
}

sub _ts {
	my ($sec, $usec) = gettimeofday();
	my ($s, $m, $h, $d, $mo, $y) = localtime($sec);
	$y  += 1900;             # vierstelliges Jahr
	$mo += 1;                # 1..12
	my $ms = int($usec / 1000);
	return sprintf("%02d.%02d.%04d %02d:%02d:%02d.%03d", $d, $mo, $y, $h, $m, $s, $ms);
}

#####################################################
# Error-Sub
#####################################################

  sub error
  {
    $template_title = $phrase->param("TXT0000") . " - " . $phrase->param("TXT0028");

    &lbheader;
    open(F,"$installfolder/templates/system/error.html") || die "Missing template system/error.html";
    while (<F>)
    {
      $_ =~ s/<!--\$(.*?)-->/${$1}/g;
      print $_;
    }
    close(F);
    &footer;
    exit;
  }
  


##########################################################################
# Small helper
##########################################################################

sub job_log_end {
    open my $lfh, '>>', "$lbplogdir/$logfile" or return;
    print $lfh "################################ End TTS Preparation #####################################\n";
    close $lfh;
}
  
  
#####################################################
# Page-Header-Sub
#####################################################

sub lbheader {
    my $helpfile = "$installfolder/templates/plugins/$psubfolder/help.html";
    open(my $F, "<", $helpfile) or die "Missing template $helpfile";
    while (<$F>) {
        $_ =~ s/<!--\$(.*?)-->/${$1}/g;
        $helptext .= $_;
    }
    close($F);

    my $headerfile = "$installfolder/templates/system/$lang/header.html";
    if (! -f $headerfile) {
        $headerfile = "$installfolder/templates/system/en/header.html";
    }

    open($F, "<", $headerfile) or die "Missing template system/en/header.html";
    while (<$F>) {
        $_ =~ s/<!--\$(.*?)-->/${$1}/g;
        print $_;
    }
    close($F);
}
  
 
#####################################################
# Footer
#####################################################

sub footer {
    my $footerfile = "$installfolder/templates/system/$lang/footer.html";
    if (! -f $footerfile) {
        $footerfile = "$installfolder/templates/system/en/footer.html";
    }

    open(my $F, "<", $footerfile) or die "Missing template system/en/footer.html";
    while (<$F>) {
        $_ =~ s/<!--\$(.*?)-->/${$1}/g;
        print $_;
    }
    close($F);
}

