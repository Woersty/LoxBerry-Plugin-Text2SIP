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

use LoxBerry::System;
use LoxBerry::Log;
use LoxBerry::IO;
use CGI qw/:standard/;
use Config::Simple '-strict';
use File::HomeDir;
use Cwd 'abs_path';
use File::Temp;
use LWP::UserAgent;
use String::ShellQuote qw(shell_quote);
use CGI::Carp qw(fatalsToBrowser);
use JSON qw(decode_json encode_json);
use Net::MQTT::Simple;
use CGI qw(param);
use warnings;
use strict;
no  strict "refs";

##########################################################################
# Variables
##########################################################################
our $cfg;
our $plugin_cfg;
our $phrase;
our $namef="";
our $value="";
our %query;
our $lang;
our $template_title;
our @help;
our $helptext="";
our $installfolder;
our $languagefile;
our $version;
our $message;
our $nexturl;
our $do="form";
my  $home = File::HomeDir->my_home;
our $psubfolder;
our $languagefileplugin;
our $phraseplugin;
our %Config;
our @config_params;
our $pluginconfigdir;
our $pluginconfigfile;
our @language_strings;
our $error="";
our $handle;
our @Text2SIPconfigfilelines="";
our @Text2SIPhostsfilelines="";
our @Text2SIPleasefilelines="";
our $Text2SIPconfigfile;
our $Text2SIPhostsfile;
our $Text2SIPleasefile;
our $Text2SIP_CFG="";
our $Text2SIP_HOSTS="";
our $Text2SIP_LEASES="";
our $cfg_stream;
our $hosts_stream;
our $tmp_cfg;
our $tmp_hosts;
our $CONTROL_PORT;
our $Text2SIP_USE;
our $req;
our $DEBUG_USE  = "off";
our $PLUGIN_USE = "off";
our $languagefile = "language.dat";
#*********************** Added by OL *************************************
our $T2S_INSTALLED = "false";
our $T2S_USE = "off";
our $ttsfile;
our $T2S_IP;
our $ffmpeg = '/usr/bin/ffmpeg';
our $T2SPlugFolder = 'Text-2-Speech';
our $T2SminVers = '1.2.1';
our $P2W_Text;
our $P2W_lang;
our $tts_ip = '192.168.50.171';
our $full_path_to_mp3;
our $mp3tmp;
my $req_topic  = 'tts-publish';
my $resp_topic = 'tts-subscribe';
my $mqtt_user;
my $mqtt_pass;
#*************************************************************************
our $res;
our $wgetbin    = "wget";
##########################################################################
# Read Settings
##########################################################################


# Version of this script
  $version = "v2025.09.09";
  
# read language
#my $lblang = lblanguage();

my $logfile 					= "Text2SIP.log";
our $log 						= LoxBerry::Log->new ( name => 'Text2SIP', filename => $lbplogdir ."/". $logfile, append => 1 );

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
  $Text2SIPconfigfile= "$pluginconfigdir/Text2SIP_Text2SIP.cfg";

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
  foreach our $template_string (@language_strings)
  {
    ${$template_string} = $phraseplugin->param($template_string);
  }
  
  #**************************************** Added by OL ************************************
	  # Check if Text-2-speech Plugin is locally installed
	  
	  my @plugins = LoxBerry::System::get_plugins();
	  #print Dumper @plugins;
	  foreach my $plugin (@plugins) {
		if ($plugin->{PLUGINDB_TITLE} eq $T2SPlugFolder) {
			if ($plugin->{PLUGINDB_VERSION} ge $T2SminVers) {
				$T2S_INSTALLED = "true";
			}
		}
	  }
	#************************************ End of added by OL ************************************
	  
##########################################################################
# Main program
##########################################################################

  if ($do eq "makecall")
  {
    print "Content-Type: text/plain\n\n";
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
    our $P2W_Text                       = "".param('P2W_Text'.$guide                      );
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
	
	#**************************** Added by OL ***************************************
	# Get saved value from config
	$T2S_USE = param('T2S_USE');

	# Banner JETZT ausgeben (ins Log, nicht ins Jobfile)
	our $TTS_PREP_WRITTEN = 0;
	if (!$TTS_PREP_WRITTEN) {
		$TTS_PREP_WRITTEN = 1;

		my $prep = 'echo "################################ Start TTS Preparation ################################" >> '.$lbplogdir.'/'.$logfile;
		system($prep);
	}

	# und JETZT erst verzweigen
	if ($T2S_USE eq 'on') {
		&t2svoice;
	} else {
		&usepico;
	}
	#************************* End of added by OL ***********************************
	    
    #if ( $DEBUG_USE eq "on" ) { system ("echo '".$cmd."' >> $lbplogdir"."/"."$logfile"); }
    #system ("echo '".$cmd."' >> $pluginjobfile");

    $cmd = 'echo "'.localtime(time).' ## Calling '.$SIPCMD_CALLED_USER.'" 2>&1 >>'.$lbplogdir."/".$logfile;
    system ("echo '".$cmd."' >> $pluginjobfile");
    
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
    
    $cmd = $sipcmd . ' -m "G.711*" '.$sipcmd_debug.' -T '.$SIPCMD_CALL_TIMEOUT.' -P sip -u "'.$SIPCMD_CALLING_USER_NUMBER.'" -c "'.$SIPCMD_CALLING_USER_PASSWORD.'" -a "'.$SIPCMD_CALLING_USER_NAME.'" -w "'.$SIPCMD_SIP_PROXY.'" -x "c'.$SIPCMD_CALLED_USER.';w'.$SIPCMD_CALL_PAUSE_BEFORE_GUIDE.';v'.$pluginwavfile.';w'.$SIPCMD_CALL_PAUSE_AFTER_GUIDE.';h" '.$debug_value.' |tee -a '.$lbplogdir."/".$logfile.$check_result;
    if ( $DEBUG_USE eq "on" ) { system ("echo Full SIPCMD command: '".$cmd."' >> $lbplogdir/$logfile"); }
	system ("chmod +x $sipcmd >> $pluginjobfile");
    system ("echo '".$cmd."' >> $pluginjobfile");
    
    $cmd = 'echo "'.localtime(time).' ## Deleting all files " 2>&1 >>'.$lbplogdir."/".$logfile;
    system ("echo '".$cmd."' >> $pluginjobfile");
    $cmd = 'rm '.$plugindatadir.'/* 2>&1 >>'.$lbplogdir."/".$logfile;
    system ("echo '".$cmd."' >> $pluginjobfile");

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
    
    $cmd = 'cat '.$sipcmdlogfile.' >>'.$lbplogdir."/".$logfile;
    system ("echo '".$cmd."' >> $pluginjobfile");
    
    $cmd = 'echo "################################ End job from '.$pluginjobfile.' " 2>&1 >>'.$lbplogdir."/".$logfile;
    system ("echo '".$cmd."' >> $pluginjobfile");
    exit;
  }
  elsif ( $do eq "test")
  {
    print "Content-Type: text/plain\n\n";
    &test;
  }
  elsif ($do eq "check_config")
  {
    print "Content-Type: text/plain\n\n";
    our $output;
    if ( param('save_data') eq 1 )
    {
      $plugin_cfg = new Config::Simple(syntax=>'ini');
      $PLUGIN_USE                       = param('PLUGIN_USE'                    );
      if ( $PLUGIN_USE ne "on" ) { $PLUGIN_USE eq "off" };
	  #**************************** Added by OL ***************************************
	  $T2S_USE                       = param('T2S_USE'                    );
      if ( $T2S_USE ne "on" ) { $T2S_USE eq "off" };
	  my $T2S_IP                       = param('T2S_IP'                    );
	  #********************************************************************************
      $DEBUG_USE                      = param('DEBUG_USE'                    );
      if ( $DEBUG_USE ne "on" ) { $DEBUG_USE eq "off" };
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
          $plugin_cfg->param('default.P2W_Text'.$i                      ,"$P2W_Text"                       );
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
	  $plugin_cfg->param('default.T2S_IP' ,"$T2S_IP" );
	  #********************************************************************************
	  
      $plugin_cfg->param('default.DEBUG_USE' ,"$DEBUG_USE" );
      if ( $plugin_cfg->write($pluginconfigfile) )
      {
        print "\n<br/>".$phraseplugin->param('TXT_SAVE_DIALOG_OK');
        print "\n<script> setTimeout( function() { location.reload(true); }, 1500); </script>\n";
        exit;
      }
      else
      {
        print "\n<br/><span class='test2sip_job_ok'>".$phraseplugin->param('TXT_SAVE_DIALOG_OK')."</span>\n";
      }
    }
    else
    {
      print "\n<br/><span class='test2sip_job_failed'>".$phraseplugin->param('TXT_SAVE_DIALOG_FAIL')."</span>\n";
    }    
  }
  else
  {
    print "Content-Type: text/html\n\n";
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

    our $vg_select                      = "";
    our $P2W_lang                       = "de";
    our $vg_id                          = 0;
    our $LAST_ID                        = 0;
    our $PLUGIN_USE                     = "off";
	#********************** Added by OL ***********************************
	our $T2S_USE                     	= "off";
	#**********************************************************************
	#our $T2S_INSTALLED                 	= "false";
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
	
      if ( $plugin_cfg )
      {
        $LAST_ID                          =  $plugin_cfg->param('default.LAST_ID'                     );
        $PLUGIN_USE                       =  $plugin_cfg->param('default.PLUGIN_USE'                  );
		#**************************************** Added by OL *********************************************
		$T2S_USE                       	  =  $plugin_cfg->param('default.T2S_USE'                  );
		$T2S_IP                       	  =  $plugin_cfg->param('default.T2S_IP'  					   );
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

            open(F,"$installfolder/templates/plugins/$psubfolder/giude_row.html") || die "Missing template /plugins/$psubfolder/giude_row.html";
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
# Voice handler (TTS Plugin vs. Local)
##########################################################################

sub t2svoice 
{
    our ($phraseplugin, $plugin_cfg, $lbplogdir);
    our (%query);

    my $REQ_TOPIC    = 'tts-publish';
    my $RESP_TOPIC   = 'tts-subscribe';
    my $HTTP_PATH    = '/plugins/text2speech/bin/mqtt_publish.php';
    my $HTTP_TIMEOUT = 30;
    my $MQTT_WAIT_S  = 10;

    my $log = sub {
        if (open my $fh, '>>', "$lbplogdir/$logfile") {
            print $fh scalar(localtime), " $_[0]\n";
            close $fh;
        }
    };

    my $join_url = sub {
        my ($base, $file) = @_;
        return '' unless $base && $file;
        $base =~ s{/$}{};
        return "$base/$file";
    };

    my $parse_t2s_json = sub {
        my ($raw) = @_;
        my $data = eval { decode_json($raw) };
        return (undef, "JSON parse error: $@") if $@;
        my $r = $data->{response} // $data;
        return ({ file => ($r->{file}//''), httpinterface => ($r->{httpinterface}//'') }, undef);
    };

    # ---- NEU: JSON-Credentials laden ----
    my $load_remote_creds_from_json = sub {
        my $f = '/opt/loxberry/config/plugins/text2sip/remote_mqtt_config.json';
        return ({}, "no json file") unless -r $f;
        my $raw = do { local $/; open my $fh, '<', $f or return ({}, "open failed"); <$fh> };
        my $j = eval { decode_json($raw) };
        return ({}, "json parse error: $@") if $@;

        # erwartete Felder (tolerant, optional)
        my %out = (
            host         => $j->{brokerhost} // $j->{host} // '',
            port         => $j->{brokerport} // $j->{port} // 1883,
            user         => $j->{brokeruser} // $j->{user} // '',
            pass         => $j->{brokerpass} // $j->{pass} // '',
            req_topic    => $j->{req_topic}    // $REQ_TOPIC,
            resp_topic   => $j->{resp_topic}   // $RESP_TOPIC,
            http_path    => $j->{http_path}    // $HTTP_PATH,
            http_timeout => $j->{http_timeout} // $HTTP_TIMEOUT,
        );
        return (\%out, undef);
    };

    # ---- Eingaben prüfen ----
    my $guide = int($query{'vg'} // param('vg') // 0);
    if ($guide == 0) {
        print $phraseplugin->param('TXT_JOB_QUEUED_INVALID_VGID'), "\n";
        print "\n<script>\$('#call_result$guide').removeClass('test2sip_job_ok').addClass('test2sip_job_failed');</script>\n";
        $log->("## ERROR: Invalid vg/guide=0");
        eval { &usepico(); };
        return;
    }

    our $P2W_Text = ''.(param('P2W_Text'.$guide) // '');
    $P2W_Text =~ s/\R//g;
    if ($P2W_Text eq '') {
        $log->("## ERROR: Empty TTS-Text");
        eval { &usepico(); };
        return;
    }

    our $P2W_lang = $P2W_lang // 'de-DE';
    my $T2S_IP = eval { $plugin_cfg->param('default.T2S_IP') } // '';

    # ---- JSON-Creds laden (für HTTP und/oder MQTT) ----
    my ($cred, $cerr) = $load_remote_creds_from_json->();
    $cred ||= {};
    my $req_topic    = $cred->{req_topic}    || $REQ_TOPIC;
    my $resp_topic   = $cred->{resp_topic}   || $RESP_TOPIC;
    my $http_path    = $cred->{http_path}    || $HTTP_PATH;
    my $http_timeout = $cred->{http_timeout} || $HTTP_TIMEOUT;

    # ===== Pfad A: Remote per HTTP, wenn T2S_IP gesetzt (nicht localhost) =====
    if ($T2S_IP ne '' && $T2S_IP !~ /^(127\.0\.0\.1|localhost)$/i) {
        my $url      = "http://$T2S_IP$http_path";
        my $safe_url = mask_secrets($url);
        $log->("## T2S via HTTP: $safe_url (text_len=".length($P2W_Text).")");

        my $ua = LWP::UserAgent->new(timeout => $http_timeout, keep_alive => 1);
        my $resp = $ua->post(
            $url,
            'Content-Type' => 'application/json',
            Content => encode_json({
                topic   => $req_topic,
                payload => { text=>$P2W_Text, nocache=>0, logging=>1, mp3files=>0 },
                retain  => 0,
                user    => ($cred->{user} // ''),
                pass    => ($cred->{pass} // ''),
            }),
        );

        my $body = $resp->decoded_content // '';
        $log->("## HTTP $safe_url -> status=".$resp->code." len=".length($body));

        unless ($resp->is_success) {
            my $snippet = substr($body, 0, 400); $snippet =~ s/\R/ /g;
            $snippet = mask_secrets($snippet);
            $log->("## ERROR: HTTP ".$resp->status_line." body(snippet): $snippet – fallback to Pico");
            eval { &usepico(); };
            return;
        }

        # JSON jetzt aus dem bereits gelesenen $body parsen
        my ($parsed, $perr) = $parse_t2s_json->($body);
        if ($perr) {
            my $snippet = substr($body, 0, 400); $snippet =~ s/\R/ /g;
            $snippet = mask_secrets($snippet);
            $log->("## ERROR: $perr body(snippet): $snippet – fallback to Pico");
            eval { &usepico(); };
            return;
        }

        our $full_path_to_mp3 = $join_url->($parsed->{httpinterface}, $parsed->{file});
        if ($full_path_to_mp3) {
            my $safe_mp3 = mask_secrets($full_path_to_mp3);
            $log->("## T2S HTTP OK: $safe_mp3");
            eval { &usetts(); };
            return;
        }
        $log->("## ERROR: T2S HTTP failed – fallback to Pico");
        eval { &usepico(); };
        return;
    }

    # ===== Pfad B: Lokal via MQTT =====
    $log->("## T2S via MQTT (local) (text_len=".length($P2W_Text).")");

    # Falls keine JSON-Creds vorhanden sind, nutze LoxBerry-Defaults
    my ($host, $port, $user, $pass) = do {
        if ($cred->{host}) {
            ($cred->{host}, $cred->{port} // 1883, $cred->{user}//'', $cred->{pass}//'')
        } else {
            my $mqttcred = LoxBerry::IO::mqtt_connectiondetails();
            (
                $mqttcred->{brokerhost} // '127.0.0.1',
                $mqttcred->{brokerport} // 1883,
                $mqttcred->{brokeruser} // '',
                $mqttcred->{brokerpass} // ''
            )
        }
    };

    # Connect-Info mit maskierten Secrets
    $log->("## MQTT connect to $host:$port user=".($user//'').' pass=***');

    $ENV{MQTT_SIMPLE_ALLOW_INSECURE_LOGIN} = 1;

    my $mqtt;
    eval {
        $mqtt = Net::MQTT::Simple->new("$host:$port");
        $mqtt->login($user, $pass) if length($user) || length($pass);
        1;
    } or do {
        $log->("## ERROR: MQTT connect/login failed ($host:$port, user=".($user//'').") – fallback to Pico");
        eval { &usepico(); };
        return;
    };

    my ($reply, $raw_msg);
    $mqtt->subscribe($resp_topic => sub {
        my ($t, $msg) = @_;
        $raw_msg //= $msg;
        my ($parsed, $perr) = $parse_t2s_json->($msg);
        return if $perr;
        $reply = $parsed if $parsed->{file} && $parsed->{httpinterface};
    });

    $mqtt->publish($req_topic, encode_json({
        text     => $P2W_Text,
        nocache  => 0,
        logging  => 1,
        mp3files => 0,
    }));

    my $deadline = time + $MQTT_WAIT_S;
    while (!defined $reply && time < $deadline) {
        $mqtt->tick();
        select undef, undef, undef, 0.1;
    }
    $mqtt->disconnect();

    if ($raw_msg && !$reply) {
        my $dump = substr($raw_msg, 0, 800); $dump =~ s/\R/ /g;
        $dump = mask_secrets($dump);
        $log->("## MQTT raw response (masked, first 800): $dump");
    }

    our $full_path_to_mp3 = '';
    if ($reply && $reply->{httpinterface} && $reply->{file}) {
        $full_path_to_mp3 = $join_url->($reply->{httpinterface}, $reply->{file});
        if ($full_path_to_mp3) {
            my $safe_mp3 = mask_secrets($full_path_to_mp3);
            $log->("## T2S MQTT OK: $safe_mp3");
            eval { &usetts(); };
            return;
        }
    }

    $log->("## WARNING: T2S MQTT no response/URL – fallback to Pico");
    eval { &usepico(); };
    return;
}



##########################################################################
# Small helper
##########################################################################

sub job_log_end {
    open my $lfh, '>>', "$lbplogdir/$logfile" or return;
    print $lfh "################################ End TTS Preparation ################################\n";
    close $lfh;
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
        print $fh scalar(localtime), " $_[0]\n";
        close $fh;
    };
	
    my $job = sub {
		my ($msg) = @_;
		my $ts   = scalar localtime;
		my $line = "$ts $msg";                 # finaler Logtext (eine Zeile)
		open my $pfh, '>>', $pluginjobfile or return;
		print $pfh 'echo ', shell_quote($line), ' >> ',
				   shell_quote("$lbplogdir/$logfile"), "\n";
		close $pfh;
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

    # --- 1) Pico: Text -> TMP-WAV ---
    $job->("## Generating voice (pico2wave)");
    my $text = $P2W_Text // ''; $text =~ s/"/\\"/g;

    my $p2w_cmd = $p2w.' -l "'.$P2W_lang.'" -w "'.$plugintmpfile.'" "'.$text.'" 2>> '.$lbplogdir.'/'.$logfile;
    $job->("pico2wave: $p2w_cmd") if ($DEBUG_USE||'') eq 'on';

    my $rc_p2w = system($p2w_cmd);
    my $sz_in  = (-e $plugintmpfile) ? (-s $plugintmpfile) : 0;
    $log->("## pico2wave rc=$rc_p2w size=$sz_inB -> $plugintmpfile");
    if ($rc_p2w != 0 || $sz_in < 128) {
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
        print $fh scalar(localtime), " $_[0]\n";
        close $fh;
    };
    my $job = sub {
		my ($msg) = @_;
		my $ts   = scalar localtime;
		my $line = "$ts $msg";                 # finaler Logtext (eine Zeile)
		open my $pfh, '>>', $pluginjobfile or return;
		print $pfh 'echo ', shell_quote($line), ' >> ',
				   shell_quote("$lbplogdir/$logfile"), "\n";
		close $pfh;
	};

    $job->("## Generating voice by T2S Plugin");
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

    # >>> Maskiertes Download-Kommando ins Jobfile
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

    # >>> Maskiertes ffmpeg-Kommando ins Jobfile
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
        job_log_end();
        return;
    }

    # --- Abschluss ---
    $job->("## Converting done");
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
