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

use strict;
use utf8;
binmode STDOUT, ":utf8";
use warnings;
no  strict 'refs';                           # nötig für ${$var}-Templateersetzung

# CGI / Fehlerausgabe
use CGI qw/:standard -utf8/;                 # header(), param(), …
use CGI::Carp qw(fatalsToBrowser);

# LoxBerry
use LoxBerry::System;
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
use JSON;

# Protokolle / Formate
use JSON qw(decode_json encode_json);
use Net::MQTT::Simple;
use Encode qw(decode_utf8 encode_utf8);
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
our ($DEBUG_USE,$PLUGIN_USE);
our ($logfile,$log);
our $HOST_IP = LoxBerry::System::get_localip();
our $T2SPlugFolder = 'text2speech';  # exact folder name of T2S master
our $wgetbin;
our $POPUP = '';
our $CONFIRM = '';
our $ffmpeg  = '/usr/bin/ffmpeg';

# T2S
our ($T2S_INSTALLED,$T2S_USE,$T2SPlugFolder,$T2SminVers,$t2s_is_installed,$BUNDLE_PATH,$BUNDLE_EXISTS,$bundlename,$bundle_path,$role_bridge,$ROLE_BRIDGE,$bundle);
our ($P2W_Text,$P2W_lang,$full_path_to_mp3,$mp3tmp,$ttsfile,$CLIENT_ID,$client);

# Pfade/Jobs/Audio
our ($logfile,$sipcmdlogfile,$pluginjobfile,$pluginwavfile,$plugintmpfile,$pluginbindir,$plugindatadir,$pico2wave,$sipcmd,$cmd);

# ----------------------------------------------------------------------
# Setup / Einlesen (wie zuvor, keine Logikänderung)
# ----------------------------------------------------------------------
$version        = "v2025.09.09";
$do             = "form";
$T2S_INSTALLED  = "false";
$T2S_USE        = "off";
$T2SPlugFolder  = "Text-2-Speech";
$T2SminVers     = "1.4.0";
$CLIENT_ID   	= "t2s-bridge";
$logfile 		= "Text2SIP.log";
$bundlename 	= "t2s_bundle.tar.gz";
$bundle_path 	= 'REPLACELBHOMEDIR/config/plugins/text2sip/bridge/' . $bundlename;
$role_bridge 	= (-e '/etc/mosquitto/role/sip-bridge') ? 'true' : 'false';

my $home 		= File::HomeDir->my_home;
$CLIENT_ID   	= "t2s-bridge";
my $hostname 	= lbhostname();
$client			= $CLIENT_ID."-".$hostname;

##########################################################################
# Read Settings
##########################################################################
  
# read language
#my $lblang = lblanguage();

our $log		= LoxBerry::Log->new ( name => 'Text2SIP', filename => $lbplogdir ."/". $logfile, append => 1 );

# Figure out in which subfolder we are installed
  $psubfolder = abs_path($0);
  $psubfolder =~ s/(.*)\/(.*)\/(.*)$/$2/g;

#Set directories + read LoxBerry config
  $cfg              = new Config::Simple("$home/config/system/general.cfg");
  $installfolder    = $cfg->param("BASE.INSTALLFOLDER");
  $lang             = $cfg->param("BASE.LANG");
  $wgetbin          = $cfg->param("BINARIES.WGET");


#Set directories + read Plugin config
  $pluginconfigdir  = "$home/config/plugins/$psubfolder";
  $pluginconfigfile = "$pluginconfigdir/Text2SIP.cfg";

  #Set directories + read Plugin config
  $pluginconfigdir  = "$home/config/plugins/$psubfolder";
    $namef =~ s/%([a-fA-F0-9][a-fA-F0-9])/pack("C", hex($1))/eg;
    $value =~ tr/+/ /;
    $value =~ s/%([a-fA-F0-9][a-fA-F0-9])/pack("C", hex($1))/eg;
    $query{$namef} = $value;
    our $sipcmdlogfile;
    our $pluginjobfile;
    our $pluginwavfile;
    our $plugintmpfile;
    our $pluginbindir;
    our $plugindatadir;
    our $pico2wave;
    our $sox;
    our $sipcmd;
    our $cmd;
    our $linefree;
    # Set variables
    $psubfolder       = abs_path($0);
    $psubfolder       =~ s/(.*)\/(.*)\/(.*)$/$2/g;

    $pico2wave        = "/usr/bin/pico2wave";
    $pluginbindir     = $installfolder."/webfrontend/htmlauth/plugins/".$psubfolder."/bin";
    $plugindatadir    = $installfolder."/data/plugins/".$psubfolder."/wav"  ;
   	mkdir $plugindatadir unless -d $plugindatadir; # Check if dir exists. If not create it.
    $sipcmdlogfile    = $installfolder."/log/plugins/".$psubfolder."/Text2SIP_sipcmd.log";
    mkdir "$installfolder/log/plugins/$psubfolder" unless -d "$installfolder/log/plugins/$psubfolder"; # Check if dir exists. If not create it.
    system ("echo -n '' > $sipcmdlogfile");
    sub get_temp_filename 
    {
      my ($suffix) = @_;
      my $fh = File::Temp->new
      (
        TEMPLATE => 'Text2SIP_XXXX',
        DIR      => $installfolder."/data/plugins/".$psubfolder."/wav/",
        SUFFIX   => $suffix
      );
      return $fh->filename;
    }
    $pluginjobfile    = get_temp_filename('.job.tsp');
    $pluginwavfile    = get_temp_filename('_wav');
    $plugintmpfile    = get_temp_filename('.tmp.wav');
    
    #$sox              = "/usr/bin/sox";
    $sipcmd           = $pluginbindir."/sipcmd";
    $plugin_cfg       = new Config::Simple("$pluginconfigfile");

  foreach (split(/&/,$ENV{'QUERY_STRING'}))
  {
    ($namef,$value) = split(/=/,$_,2);
    $namef =~ tr/+/ /;
    $namef =~ s/%([a-fA-F0-9][a-fA-F0-9])/pack("C", hex($1))/eg;
    $value =~ tr/+/ /;
    $value =~ s/%([a-fA-F0-9][a-fA-F0-9])/pack("C", hex($1))/eg;
    $query{$namef} = $value;
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
  
	#**************************************** Added by OL (Bundle check + conditional SIP install) ************************************

	# (1) Detect if Text2Speech (T2S) plugin is installed
	my $T2SPlugFolder = 'text2speech';  # exact folder name of T2S master
	my $T2SminVers    = '0.0.0';        # optional version check

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
	#************************************ End of added by OL (Bundle check + conditional SIP install) ************************************

	  
##########################################################################
# Main program
##########################################################################

  if ($do eq "makecall")
  {
    print header(-type => 'text/plain', -charset => 'UTF-8');
    our $check_result ="";
    my $guide                           = int($query{'vg'});
	$ENV{SDL_AUDIODRIVER} = 'dummy';  # verhindert ALSA-Init von ffplay/SDL
    if ( $guide == 0 )
    {
      print ( $phraseplugin->param('TXT_JOB_QUEUED_INVALID_VGID') );
      print "\n<script> \$('#call_result".$guide."').removeClass( 'test2sip_job_ok' ).addClass( 'test2sip_job_failed' ); </script>\n";
      exit;
    }
    our $P2W_lang                       = "".param('P2W_lang'.$guide                      );
    if ($P2W_lang ne "gb" && $P2W_lang ne "us" && $P2W_lang ne "es" && $P2W_lang ne "fr" &&  $P2W_lang ne "it" ) {$P2W_lang = "de"};
	my $raw_txt 						= "".param('P2W_Text'.$guide					  );
	$P2W_Text   = defined $raw_txt ? $raw_txt : '';
    our $SIPCMD_CALLING_USER_NUMBER     = "".param('SIPCMD_CALLING_USER_NUMBER'.$guide    );
    our $SIPCMD_CALLING_USER_PASSWORD   = "".param('SIPCMD_CALLING_USER_PASSWORD'.$guide  );
    our $SIPCMD_CALLING_USER_NAME       = "".param('SIPCMD_CALLING_USER_NAME'.$guide      );
    our $SIPCMD_SIP_PROXY               = "".param('SIPCMD_SIP_PROXY'.$guide              );
    our $SIPCMD_CALLED_USER             = "".param('SIPCMD_CALLED_USER'.$guide            );
    our $SIPCMD_CALL_PAUSE_BEFORE_GUIDE = "".param('SIPCMD_CALL_PAUSE_BEFORE_GUIDE'.$guide);
    our $SIPCMD_CALL_PAUSE_AFTER_GUIDE  = "".param('SIPCMD_CALL_PAUSE_AFTER_GUIDE'.$guide );
    our $SIPCMD_CALL_RESULT_VI          = "".param('SIPCMD_CALL_RESULT_VI'.$guide         );
    our $SIPCMD_CALL_TIMEOUT            = int(param('SIPCMD_CALL_TIMEOUT'.$guide          ));
    our $SIPCMD_MSINFO                  = "".param('SIPCMD_MSINFO'.$guide                 );
    our $SIPCMD_CONFIRMATION_DIGIT      = "".param('SIPCMD_CONFIRMATION_DIGIT'.$guide     );
    if ($SIPCMD_CONFIRMATION_DIGIT =~ /[0-9\*\#]/ ) 
    {
    	$SIPCMD_CONFIRMATION_DIGIT = $SIPCMD_CONFIRMATION_DIGIT;
    }
    else
    {
    	$SIPCMD_CONFIRMATION_DIGIT = "-";
    };

 		my $unknown = "unbekannt";
    if     ($P2W_lang eq "gb" ) { $P2W_lang = "en-GB"; $unknown = "unknown" }
    elsif  ($P2W_lang eq "us" ) { $P2W_lang = "en-US"; $unknown = "unknown" }
    elsif  ($P2W_lang eq "es" ) { $P2W_lang = "es-ES"; $unknown = "desconocido" }
    elsif  ($P2W_lang eq "fr" ) { $P2W_lang = "fr-FR"; $unknown = "inconnu" }
    elsif  ($P2W_lang eq "it" ) { $P2W_lang = "it-IT"; $unknown = "sconosciuto" }
    elsif  ($P2W_lang eq "de" ) { $P2W_lang = "de-DE"; $unknown = "unbekannt" }
    else 
    { 
      LOGERR "Error: Unknown language $P2W_lang - using german instead ";
      $P2W_lang = "de-DE";
    }
    
    if ( "$SIPCMD_MSINFO" ne "" )
   	{
   		my $msinfo = `$wgetbin -a  $lbplogdir."/".$logfile --retry-connrefused --tries=2 --waitretry=1 --timeout=1 --passive-ftp -nH -qO- "$SIPCMD_MSINFO" 2>&1|grep value|cut -d'"' -f4`;
		  if ($? ne 0 ) 
		  {
		  	my $text = $phraseplugin->param('ERROR0006')." ".$SIPCMD_MSINFO." ".$msinfo;
		    `echo "$text " >> $lbplogdir."/".$logfile`;
				$P2W_Text = $P2W_Text =~ s/##/${unknown}/gr; 
		  } 
		  else 
		  {
		  	my $text = $phraseplugin->param('TXT_SIPCMD_READ_MS_STATE')." ".$msinfo;
	      `echo "$text " >>  $lbplogdir."/".$logfile`;
		    $P2W_Text = $P2W_Text =~ s/##/$msinfo/gr; 
		  }
    }
		$P2W_Text = $P2W_Text =~ s/\n//gr; 
    `echo "Text: $P2W_Text " >>  $lbplogdir."/".$logfile`;
        
    $cmd = 'echo "################################ Create job to '.$pluginjobfile.' @ '.localtime(time).' " 2>&1 >>'.$lbplogdir."/".$logfile;
    if ( $DEBUG_USE eq "on" ) { system ("echo '".$cmd."' >> $lbplogdir."/".$logfile"); }
    $cmd = 'echo "################################ Start job from '.$pluginjobfile.' @ '.localtime(time).' " 2>&1 >>'.$lbplogdir."/".$logfile;
    system ("echo '".$cmd."' >> $pluginjobfile");
	
	#**************************** TTS routing (CONFIG-ONLY) ****************************
	# DO NOT read CGI param here. Always use saved plugin config.
	my $cfg_flag = eval { $plugin_cfg->param('default.T2S_USE') } // 'off';
	$cfg_flag = lc($cfg_flag // 'off'); $cfg_flag =~ s/^\s+|\s+$//g;

	# Banner + Marker nur einmal
	our $TTS_PREP_WRITTEN = 0;
	if (!$TTS_PREP_WRITTEN) {
		$TTS_PREP_WRITTEN = 1;
		system('echo "################################ Start TTS Preparation ################################" >> ' .
			   $lbplogdir . '/' . $logfile);
	}

	# Klarer Log, was passiert
	my $ts_now = _ts();
	system('echo "'.$ts_now.' ## T2S_USE (config): ' . $cfg_flag . '" >> ' . $lbplogdir . '/' . $logfile);

	# HARTE Marker vor/nach t2svoice, damit man es *immer* sieht
	system('echo "'.$ts_now.' ## ROUTE: about to call t2svoice()" >> ' . $lbplogdir . '/' . $logfile) if $cfg_flag eq 'on';

	if ($cfg_flag eq 'on') {
        our $t2s_suppress_fallback = 0;   # << NEU: Standard = kein Suppress
        &t2svoice();   # T2S (MQTT/mTLS oder lokal)

        # Wenn t2svoice keine WAV erzeugt hat, Fallback (außer t2svoice möchte bewusst stumm bleiben)
        if ( !$t2s_suppress_fallback && ( !-e $pluginwavfile || -s $pluginwavfile <= 0 ) ) {
            system('echo "## ROUTE: t2svoice produced no WAV -> fallback to Pico" >> ' . $lbplogdir . '/' . $logfile);
            &usepico();
        }
    } else {
        &usepico();    # Pico
    }

	#************************** End TTS routing (CONFIG-ONLY) ***************************

    # --- WICHTIG: Full SIPCMD command *NACH* End TTS Preparation loggen ---
    $DEBUG_USE                      = param('DEBUG_USE'                    );
    if ( $DEBUG_USE ne "on" ) { $DEBUG_USE = "off" };
    our $debug_value  ='2>/dev/null';
    our $sipcmd_debug ='';
    if ( $DEBUG_USE eq "on" )
    {
    	$sipcmd_debug = "-o $sipcmdlogfile";
      $debug_value  = '2>&1';
    }
    if ( $SIPCMD_CALL_RESULT_VI ne "" && substr($SIPCMD_CALL_RESULT_VI,0,7) eq "http://")
    {
      $check_result = '|while read DTMF_LINE; do echo $DTMF_LINE|grep -q "Exiting."; if [ $? -eq 0 ]; then wget -q -t 1 -T 10 -O /dev/null "'.$SIPCMD_CALL_RESULT_VI.'0"; fi; DTMF_CODE=`echo $DTMF_LINE |grep "receive DTMF:"|cut -c16`; echo "DTMF: $DTMF_CODE"; wget -q -t 1 -T 10 -O /dev/null "'.$SIPCMD_CALL_RESULT_VI.'$DTMF_CODE"; echo $DTMF_LINE|grep -q "receive DTMF:";  if [ "$DTMF_CODE" == "'.$SIPCMD_CONFIRMATION_DIGIT.'" ]; then echo "Confirmation code '.$SIPCMD_CONFIRMATION_DIGIT.' detected. Exit!!" >> '.$lbplogdir."/".$logfile.'; sleep .5; killall -15 '.$sipcmd.'; else if [ ${#DTMF_CODE} -eq 1 ]; then echo "Confirmation code [$DTMF_CODE] detected but ['.$SIPCMD_CONFIRMATION_DIGIT.'] expected. Continue..." >> '.$lbplogdir."/".$logfile.'; fi; fi; done ';     
    } 
    if ( $SIPCMD_CALL_TIMEOUT < 1 ) { $SIPCMD_CALL_TIMEOUT = 60 };
	
    # 🟢 INSERT WRAPPER ACTIVATION HERE:
	$ENV{'MASTER_IP'}          = $HOST_IP;
	$ENV{'OPAL_INTERFACE'}     = $HOST_IP;

	# Exclude docker0 + Docker default CIDR; also append concrete docker0 IP if present
	$ENV{'OPAL_IFACE_EXCLUDE'} = 'docker0,172.16.0.0/12';

	my $docker_ip = `ip -4 addr show docker0 | grep -oP '(?<=inet\\s)\\d+(\\.\\d+){3}'`;
	chomp $docker_ip;
	if ($docker_ip) {
		$ENV{'OPAL_IFACE_EXCLUDE'} .= ",$docker_ip";
	}
	$sipcmd = $lbphtmlauthdir.'/bin/sipcall_wrapper.pl';

    # Continue with the normal command construction
    $cmd = $sipcmd
          . ' -m "G.711*" ' . $sipcmd_debug
          . ' -T ' . $SIPCMD_CALL_TIMEOUT
          . ' -P sip'
          . ' -u "' . $SIPCMD_CALLING_USER_NUMBER . '"'
          . ' -c "' . $SIPCMD_CALLING_USER_PASSWORD . '"'
          . ' -a "' . $SIPCMD_CALLING_USER_NAME . '"'
          . ' -w "' . $SIPCMD_SIP_PROXY . '"'
          . ' -x "c' . $SIPCMD_CALLED_USER
          . ';w' . $SIPCMD_CALL_PAUSE_BEFORE_GUIDE
          . ';v' . $pluginwavfile
          . ';w' . $SIPCMD_CALL_PAUSE_AFTER_GUIDE
          . ';h" '
          . $debug_value
          . ' | tee -a ' . $lbplogdir . '/' . $logfile . $check_result;

    # Immer loggen – und ZWAR NACH dem TTS-Footer:
    system ("echo ## Full SIPCMD command: '".$cmd."' >> $lbplogdir/$logfile");

	# Erst jetzt: Start-Header in das Jobfile schreiben (damit Reihenfolge stimmt)
    my $job_hdr = 'echo "################################ Start job from '.$pluginjobfile.' @ $(date)" 2>&1 >>'.$lbplogdir.'/'.$logfile;
    system('echo ' . $job_hdr . ' >> ' . $pluginjobfile);

	system ("chmod +x $sipcmd >> $pluginjobfile");
    system ("echo '".$cmd."' >> $pluginjobfile");
    
    my $delmsg = 'echo "'._ts().' ## Deleting all files " 2>&1 >>'.$lbplogdir."/".$logfile;
    system ("echo '".$delmsg."' >> $pluginjobfile");
    my $delcmd = 'rm '.$plugindatadir.'/* 2>&1 >>'.$lbplogdir."/".$logfile;
    system ("echo '".$delcmd."' >> $pluginjobfile");

    system ("echo -n 'Add job for guide ".$guide." to queue as #' 2>&1 >>$lbplogdir/$logfile");
    system ("tsp bash $pluginjobfile  2>&1 >>$lbplogdir/$logfile");
    if ( $? eq "0" )
    {
      print "\n<br/>".$phraseplugin->param('TXT_JOB_QUEUED_OK');
      print "\n<script> \$('#call_result".$guide."').removeClass( 'test2sip_job_failed' ).addClass( 'test2sip_job_ok' ); </script>\n";
    }
    else
    {
      print "\n<br/>".$phraseplugin->param('TXT_JOB_QUEUED_FAIL');
      print "\n<script> \$('#call_result".$guide."').removeClass( 'test2sip_job_ok' ).addClass( 'test2sip_job_failed' ); </script>\n";
    }
    
    my $catcmd = 'cat '.$sipcmdlogfile.' >>'.$lbplogdir."/".$logfile;
    system ("echo '".$catcmd."' >> $pluginjobfile");
    
    my $job_end = 'echo "################################ End job from '.$pluginjobfile.' " 2>&1 >>'.$lbplogdir."/".$logfile;
    system ("echo '".$job_end."' >> $pluginjobfile");
    exit;
  #--------------- Test -----------------	
  }
  elsif ( $do eq "test")
  {
    print header(-type => 'text/plain', -charset => 'UTF-8');
    &test;
  }
  
  
#--------------- T2S Status JSON ---------------
elsif ($do eq "get_t2s_status")
{
    use utf8;
    binmode STDOUT, ':encoding(UTF-8)';
    print header(-type => 'application/json', -charset => 'UTF-8');

    my $role_bridge = "/etc/mosquitto/role/sip-bridge";
    my $healthfile  = "REPLACELBHOMEDIR/log/plugins/text2sip/health.json";
    my %result      = ( mode => "local" );

    # Wenn Bridge-Rolle erkannt
    if (-e $role_bridge) {
        $result{mode} = "bridge";

        if (-f $healthfile) {
            eval {
                require JSON;
                require File::Slurp;
                require Time::Piece;

                my $rawfile = File::Slurp::read_file($healthfile);
                my $data    = JSON::decode_json($rawfile);

                if ($data->{last_handshake}) {

                    my $raw = $data->{last_handshake};
                    my $tp;

                    # ---------------------------------------------------
                    # 1. ISO 8601 Versuch: 2025-11-13T11:45:02+01:00
                    # ---------------------------------------------------
                    eval {
                        $tp = Time::Piece->strptime($raw, '%Y-%m-%dT%H:%M:%S');
                    };

                    # ---------------------------------------------------
                    # 2. Classic Format: 2025-11-13 11:45:02
                    # ---------------------------------------------------
                    if (!$tp) {
                        eval {
                            $tp = Time::Piece->strptime($raw, '%Y-%m-%d %H:%M:%S');
                        };
                    }

                    # ---------------------------------------------------
                    # 3. Format für UI
                    # ---------------------------------------------------
                    if ($tp) {
                        # [YYYY-MM-DD] HH:MM:SS
                        my $pretty = sprintf(
                            '[%04d-%02d-%02d] %02d:%02d:%02d',
                            $tp->year, $tp->mon, $tp->mday,
                            $tp->hour, $tp->min, $tp->sec
                        );

                        $result{last} = $pretty;
                        $result{age}  = time - $tp->epoch;
                    }
                }
            };
        }
    }

    require JSON;
    print JSON::encode_json(\%result);
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
          our $P2W_lang                       = "".param('P2W_lang'.$i                      );
          if ($P2W_lang ne "gb" && $P2W_lang ne "us" && $P2W_lang ne "es" && $P2W_lang ne "fr" &&  $P2W_lang ne "it" ) {$P2W_lang = "de"};
          our $P2W_Text                       = "".param('P2W_Text'.$i                      );
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
          $plugin_cfg->param('default.P2W_Text'.$i, $P2W_Text);
          $plugin_cfg->param('default.SIPCMD_CALLING_USER_NUMBER'.$i    ,"$SIPCMD_CALLING_USER_NUMBER"     );
          $plugin_cfg->param('default.SIPCMD_CALLING_USER_PASSWORD'.$i  ,"$SIPCMD_CALLING_USER_PASSWORD"   );
          $plugin_cfg->param('default.SIPCMD_CALLING_USER_NAME'.$i      ,"$SIPCMD_CALLING_USER_NAME"       );
          $plugin_cfg->param('default.SIPCMD_SIP_PROXY'.$i              ,"$SIPCMD_SIP_PROXY"               );
          $plugin_cfg->param('default.SIPCMD_CALLED_USER'.$i            ,"$SIPCMD_CALLED_USER"             );
          $plugin_cfg->param('default.SIPCMD_CALL_PAUSE_BEFORE_GUIDE'.$i,"$SIPCMD_CALL_PAUSE_BEFORE_GUIDE" );
          $plugin_cfg->param('default.SIPCMD_CALL_PAUSE_AFTER_GUIDE'.$i ,"$SIPCMD_CALL_PAUSE_AFTER_GUIDE"  );
          $plugin_cfg->param('default.SIPCMD_CALL_RESULT_VI'.$i         ,"$SIPCMD_CALL_RESULT_VI"          );
          $plugin_cfg->param('default.SIPCMD_CALL_TIMEOUT'.$i           ,"$SIPCMD_CALL_TIMEOUT"            );
          $plugin_cfg->param('default.SIPCMD_CONFIRMATION_DIGIT'.$i     ,"$SIPCMD_CONFIRMATION_DIGIT"      );
          $plugin_cfg->param('default.SIPCMD_MSINFO'.$i                 ,"$SIPCMD_MSINFO"                  );
        }
      }
	  
	  $plugin_cfg->param('default.LAST_ID'    ,$LAST_ID    );
      $plugin_cfg->param('default.PLUGIN_USE' ,"$PLUGIN_USE" );
	  
	  #**************************** Added by OL ***************************************
	  $plugin_cfg->param('default.T2S_USE' ,"$T2S_USE" );
	  $plugin_cfg->param('default.BRIDGE_USER' ,"$client" );
	  #********************************************************************************
	  
      $plugin_cfg->param('default.DEBUG_USE' ,"$DEBUG_USE" );
	  
	  my $version = LoxBerry::System::pluginversion();
	  $plugin_cfg->param('default.INSTALLED_VERSION', $version);
	  
	  install_sip_bridge($T2S_INSTALLED, $T2S_USE, $client);
	  	  
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
		#**************************************** Added by OL *********************************************
		$T2S_USE                       	  =  $plugin_cfg->param('default.T2S_USE'                  );
		$BUNDLE_PATH   					  =  $bundle_path;
		$BUNDLE_EXISTS 					  =  (-f $bundle_path) ? "true" : "false";
		$ROLE_BRIDGE					  =  $role_bridge;
		#**************************************************************************************************
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
            $P2W_Text                       =  "".$plugin_cfg->param('default.P2W_Text'.$vg_id                          );
            $SIPCMD_CALLING_USER_NUMBER     =  "".$plugin_cfg->param('default.SIPCMD_CALLING_USER_NUMBER'.$vg_id        );
            $SIPCMD_CALLING_USER_PASSWORD   =  "".$plugin_cfg->param('default.SIPCMD_CALLING_USER_PASSWORD'.$vg_id      );
            $SIPCMD_CALLING_USER_NAME       =  "".$plugin_cfg->param('default.SIPCMD_CALLING_USER_NAME'.$vg_id          );
            $SIPCMD_SIP_PROXY               =  "".$plugin_cfg->param('default.SIPCMD_SIP_PROXY'.$vg_id                  );
            $SIPCMD_CALLED_USER             =  "".$plugin_cfg->param('default.SIPCMD_CALLED_USER'.$vg_id                );
            $SIPCMD_CALL_PAUSE_BEFORE_GUIDE =  int($plugin_cfg->param('default.SIPCMD_CALL_PAUSE_BEFORE_GUIDE'.$vg_id   ));
            $SIPCMD_CALL_PAUSE_AFTER_GUIDE  =  int($plugin_cfg->param('default.SIPCMD_CALL_PAUSE_AFTER_GUIDE'.$vg_id    ));
            $SIPCMD_CALL_RESULT_VI          =  "".$plugin_cfg->param('default.SIPCMD_CALL_RESULT_VI'.$vg_id             );
            $SIPCMD_CALL_TIMEOUT            =  int($plugin_cfg->param('default.SIPCMD_CALL_TIMEOUT'.$vg_id              ));
            $SIPCMD_MSINFO                  =  "".$plugin_cfg->param('default.SIPCMD_MSINFO'.$vg_id                     );
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

    $log->("################################ Start TTS Preparation ################################");

    # ----------------------------------------------------------------------
    # 1) Basic TTS parameters / sanity checks
    # ----------------------------------------------------------------------
    our $client;
    $client //= "t2s-bridge-unknown";

    my $req_topic  = "tts-publish/$client";
    my $resp_topic = "tts-subscribe/$client";

    $log->("## Using client='$client'");
    $log->("## Request topic  = $req_topic");
    $log->("## Response topic = $resp_topic");

    # Ensure text exists, otherwise Pico fallback
    $P2W_Text //= '';
    $P2W_Text =~ s/\R//g;   # remove newlines

    if ($P2W_Text eq '') {
        $log->("## Empty TTS text – using Pico fallback");
        return usepico();
    }

    # ----------------------------------------------------------------------
    # 2) Build payload (NO corr ANYMORE)
    # ----------------------------------------------------------------------
    my $payload_json = encode_json({
        text     => "$P2W_Text",
        nocache  => 0,
        logging  => 1,
        mp3files => 0,
        client   => $client,
        reply_to => $resp_topic,
    });

    $log->("## T2S payload prepared (without corr)");

    # ----------------------------------------------------------------------
    # 3) Response parser (generic, no corr matching)
    # ----------------------------------------------------------------------
    my $parse_response = sub {
        my ($msg) = @_;

        my $d = eval { decode_json($msg) };
        if ($@ || !$d || ref $d ne 'HASH') {
            $log->("## ERROR: Invalid JSON in T2S response: $@");
            return undef;
        }

        my $r = $d->{response} // $d;

        # Master-level error
        if (defined $r->{status} && $r->{status} eq 'error') {
            my $err = $r->{message} // 'unknown error';
            $log->("## MQTT T2S returned ERROR: $err");
            our $t2s_abort_all = 1;
            return undef;
        }

        my $file = $r->{file};
        my $http = $r->{interfaces}->{httpinterface} // $r->{httpinterface};

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
    # 4) Connect to local MQTT broker (bridge → master)
    # ----------------------------------------------------------------------
    $log->("## Using local MQTT broker (will be bridged to master)");

    my ($host, $port, $user, $pass) = do {
        my $cred = LoxBerry::IO::mqtt_connectiondetails();
        (
            $cred->{brokerhost} // '127.0.0.1',
            $cred->{brokerport} // 1883,
            $cred->{brokeruser} // '',
            $cred->{brokerpass} // '',
        );
    };

    $ENV{MQTT_SIMPLE_ALLOW_INSECURE_LOGIN} = 1;

    my $mqtt;
    eval {
        $mqtt = Net::MQTT::Simple->new("$host:$port");
        $mqtt->login($user, $pass) if $user || $pass;
        1;
    } or do {
        $log->("## MQTT connect/login failed – using Pico fallback");
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

        # NO corr matching anymore – first valid response wins
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
    # 8) Wait for response (or timeout) — NO ABORT ANYMORE
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
	my $text = $P2W_Text // '';

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

# ==========================================================
# Text2SIP: install SIP bridge if T2S_USE = ON and T2S exists
# ==========================================================

sub install_sip_bridge {
    my ($T2S_INSTALLED, $T2S_USE, $client) = @_;

    # Globale Variablen aus Header
    our ($bundle_path, $bundlename);

    my $installer = 'REPLACELBHOMEDIR/webfrontend/htmlauth/plugins/text2sip/bin/install_sip_client.pl';
    my $logfile   = 'REPLACELBHOMEDIR/log/plugins/text2sip/client_install.log';

    # Bridge enabled?
    return unless ($T2S_USE // '') =~ /^(?:1|on|true|yes)$/i;

    # T2S Master NOT installed on SIP client
    return unless ($T2S_INSTALLED // '') =~ /^(?:0|off|false|no)$/i;

    # Bundle + installer present
    return unless -r $bundle_path && -f $installer;

    # Installer starten mit --user Übergabe
    system("$^X '$installer' --bundle '$bundle_path' --user '$client' >>'$logfile' 2>&1");

    # Kurze Pause, dann optional user-sync (praktisch nicht mehr nötig)
    sleep 2;

    # Optional (Safe-Double-Check): sync_script bleibt drin, macht aber i. d. R. nichts mehr
    system("REPLACELBHOMEDIR/webfrontend/htmlauth/plugins/text2sip/bin/sync_bridge_user.pl >> /dev/shm/handshake_test.log 2>&1");
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

sub _read_master_ip_from_tar {
    my ($tar) = @_;
    return undef unless defined $tar && -r $tar;

    # Find master.info (top or subfolder)
    my $list = `tar -tzf '$tar' 2>/dev/null`;
    my $rc   = $?;
    return undef if $rc != 0 || !$list;

    my $mi_path;
    if ($list =~ m{^(.*?/)?master\.info\s*$}m) {
        $mi_path = ($1 // '') . 'master.info';
        $mi_path =~ s{^\./}{};
    } else {
        _dbg('WARN', 'master.info not found in bundle');
        return undef;
    }

    # Extract and parse MASTER_IP
    my $info = `tar -xOf '$tar' '$mi_path' 2>/dev/null`;
    $rc = $?;
    return undef if $rc != 0 || !$info;

    for my $line (split /\R/, $info) {
        next if $line =~ /^\s*#/;
        if ($line =~ /^\s*MASTER_IP\s*[:=]\s*(\d{1,3}(?:\.\d{1,3}){3})\s*$/) {
            my $ip = $1;
            _dbg('INFO', "Parsed MASTER_IP=$ip from master.info");
            return $ip;
        }
    }

    _dbg('WARN', 'No MASTER_IP line found in master.info');
    return undef;
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

