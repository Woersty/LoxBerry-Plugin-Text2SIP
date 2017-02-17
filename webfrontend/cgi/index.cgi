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

use CGI::Carp qw(fatalsToBrowser);
use CGI qw/:standard/;
use Config::Simple '-strict';
use File::HomeDir;
use Data::Dumper;
use Cwd 'abs_path';
use HTML::Entities;
use URI::Escape;
use MIME::Base64 qw( decode_base64 );
use Time::HiRes qw(usleep);
use File::Temp;
use warnings;
use strict;
no  strict "refs"; # we need it for template system

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
our $wgetbin    = "wget";
##########################################################################
# Read Settings
##########################################################################


# Version of this script
  $version = "0.5debug";

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
    our $pluginlogfile;
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
    $pluginbindir     = $installfolder."/webfrontend/cgi/plugins/".$psubfolder."/bin";
    $plugindatadir    = $installfolder."/data/plugins/".$psubfolder."/wav"  ;
   	mkdir $plugindatadir unless -d $plugindatadir; # Check if dir exists. If not create it.
    $pluginlogfile    = $installfolder."/log/plugins/".$psubfolder."/Text2SIP.log";
    $sipcmdlogfile    = $installfolder."/log/plugins/".$psubfolder."/Text2SIP_sipcmd.log";

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
    
    $sox              = "/usr/bin/sox";
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
  # If there's no language phrases file for choosed language, use german as default
  if (!-e "$installfolder/templates/system/$lang/language.dat")
  {
    $lang = "de";
  }

# Read translations / phrases
  $languagefile       = "$installfolder/templates/system/$lang/language.dat";
  $phrase             = new Config::Simple($languagefile);
  $languagefileplugin = "$installfolder/templates/plugins/$psubfolder/$lang/language.dat";
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


##########################################################################
# Main program
##########################################################################

  if ($do eq "makecall")
  {
    print "Content-Type: text/plain\n\n";
    our $check_result ="";
    my $guide                           = int($query{'vg'});
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
      `echo "Error: Unknown language $P2W_lang - using german instead " >> $pluginlogfile`;
      $P2W_lang = "de-DE";
    }
    
    if ( "$SIPCMD_MSINFO" ne "" )
   	{
   		my $msinfo = `$wgetbin -a $pluginlogfile --retry-connrefused --tries=2 --waitretry=1 --timeout=1 --passive-ftp -nH -qO- "$SIPCMD_MSINFO" 2>&1|grep value|cut -d'"' -f4`;
		  if ($? ne 0 ) 
		  {
		  	my $text = $phraseplugin->param('ERROR0006')." ".$SIPCMD_MSINFO." ".$msinfo;
		    `echo "$text " >> $pluginlogfile`;
				$P2W_Text = $P2W_Text =~ s/##/${unknown}/r; 
		  } 
		  else 
		  {
		  	my $text = $phraseplugin->param('TXT_SIPCMD_READ_MS_STATE')." ".$msinfo;
	      `echo "$text " >>  $pluginlogfile`;
		    $P2W_Text = $P2W_Text =~ s/##/$msinfo/r; 
		  }
    }
       
    
    $cmd = 'echo "################################ Create job to '.$pluginjobfile.' @ '.localtime(time).' " 2>&1 >>'.$pluginlogfile;
    if ( $DEBUG_USE eq "on" ) { system ("echo '".$cmd."' >> $pluginlogfile"); }
    $cmd = 'echo "################################ Start job from '.$pluginjobfile.' @ '.localtime(time).' " 2>&1 >>'.$pluginlogfile;
    system ("echo '".$cmd."' >> $pluginjobfile");

    $cmd = 'echo "'.localtime(time).' ## Generating voice " 2>&1 >>'.$pluginlogfile;
    system ("echo '".$cmd."' >> $pluginjobfile");
    $cmd = $pico2wave . ' -l "'.$P2W_lang.'" -w "'.$plugintmpfile.'" "'.$P2W_Text.'" 2>&1 >>'.$pluginlogfile;
    if ( $DEBUG_USE eq "on" ) { system ("echo '".$cmd."' >> $pluginlogfile"); }
    system ("echo '".$cmd."' >> $pluginjobfile");

    $cmd = 'echo "'.localtime(time).' ## Converting voice " 2>&1 >>'.$pluginlogfile;
    system ("echo '".$cmd."' >> $pluginjobfile");
    $cmd = $sox  . ' -v 0.9 "'.$plugintmpfile.'" -t wav -b 16 -r 8000 "'.$pluginwavfile.'" 2>&1 >>'.$pluginlogfile;
    if ( $DEBUG_USE eq "on" ) { system ("echo '".$cmd."' >> $pluginlogfile"); }
    system ("echo '".$cmd."' >> $pluginjobfile");

    $cmd = 'echo "'.localtime(time).' ## Calling '.$SIPCMD_CALLED_USER.'" 2>&1 >>'.$pluginlogfile;
    system ("echo '".$cmd."' >> $pluginjobfile");
    
    $DEBUG_USE                      = param('DEBUG_USE'                    );
    if ( $DEBUG_USE ne "on" ) { $DEBUG_USE = "off" };
    our $debug_value  ='2>/dev/null';
    if ( $DEBUG_USE eq "on" )
    {
      $debug_value = '2>&1';
    }
    if ( $SIPCMD_CALL_RESULT_VI ne "" && substr($SIPCMD_CALL_RESULT_VI,0,7) eq "http://")
    {
      $check_result = '|while read DTMF_LINE; do echo $DTMF_LINE|grep -q "Exiting."; if [ $? -eq 0 ]; then wget -q -t 1 -T 10 -O /dev/null "'.$SIPCMD_CALL_RESULT_VI.'0"; fi; DTMF_CODE=`echo $DTMF_LINE |grep "receive DTMF:"|cut -c16`; echo "DTMF: $DTMF_CODE"; wget -q -t 1 -T 10 -O /dev/null "'.$SIPCMD_CALL_RESULT_VI.'$DTMF_CODE"; echo $DTMF_LINE|grep -q "receive DTMF:";  if [ "$DTMF_CODE" == "'.$SIPCMD_CONFIRMATION_DIGIT.'" ]; then echo "Confirmation code '.$SIPCMD_CONFIRMATION_DIGIT.' detected. Exit!!" >> '.$pluginlogfile.'; sleep .5; killall -15 '.$sipcmd.'; else if [ ${#DTMF_CODE} -eq 1 ]; then echo "Confirmation code [$DTMF_CODE] detected but ['.$SIPCMD_CONFIRMATION_DIGIT.'] expected. Continue..." >> '.$pluginlogfile.'; fi; fi; done ';     
    } 
    if ( $SIPCMD_CALL_TIMEOUT < 1 ) { $SIPCMD_CALL_TIMEOUT = 60 };
    $cmd = $sipcmd . ' -o '.$sipcmdlogfile.' -T '.$SIPCMD_CALL_TIMEOUT.' -P sip -u "'.$SIPCMD_CALLING_USER_NUMBER.'" -c "'.$SIPCMD_CALLING_USER_PASSWORD.'" -a "'.$SIPCMD_CALLING_USER_NAME.'" -w "'.$SIPCMD_SIP_PROXY.'" -x "c'.$SIPCMD_CALLED_USER.';w'.$SIPCMD_CALL_PAUSE_BEFORE_GUIDE.';v'.$pluginwavfile.';w'.$SIPCMD_CALL_PAUSE_AFTER_GUIDE.';h" '.$debug_value.' |tee -a '.$pluginlogfile.$check_result;
    if ( $DEBUG_USE eq "on" ) { system ("echo '".$cmd."' >> $pluginlogfile"); }
    system ("echo '".$cmd."' >> $pluginjobfile");

    $cmd = 'echo "'.localtime(time).' ## Deleting files " 2>&1 >>'.$pluginlogfile;
    system ("echo '".$cmd."' >> $pluginjobfile");
    $cmd = 'rm -f '.$pluginjobfile.' '.$plugintmpfile.' '.$pluginwavfile.' 2>&1 >>'.$pluginlogfile;
    system ("echo '".$cmd."' >> $pluginjobfile");

    system ("echo -n 'Add job for guide ".$guide." to queue as #' 2>&1 >>$pluginlogfile");
    system ("tsp bash $pluginjobfile  2>&1 >>$pluginlogfile");
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
    $cmd = 'echo "################################ End job from '.$pluginjobfile.' " 2>&1 >>'.$pluginlogfile;
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
      if ( $PLUGIN_USE ne "on" ) { $PLUGIN_USE = "off" };
      $DEBUG_USE                      = param('DEBUG_USE'                    );
      if ( $DEBUG_USE ne "on" ) { $DEBUG_USE = "off" };
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

            open(F,"$installfolder/templates/plugins/$psubfolder/$lang/giude_row.html") || die "Missing template /plugins/$psubfolder/$lang/giude_row.html";
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
      open(F,"$installfolder/templates/plugins/$psubfolder/$lang/settings.html") || die "Missing template plugins/$psubfolder/$lang/settings.html";
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
    open(F,"$installfolder/templates/system/$lang/error.html") || die "Missing template system/$lang/error.html";
    while (<F>)
    {
      $_ =~ s/<!--\$(.*?)-->/${$1}/g;
      print $_;
    }
    close(F);
    &footer;
    exit;
  }

#####################################################
# Page-Header-Sub
#####################################################

  sub lbheader
  {
     # Create Help page
    open(F,"$installfolder/templates/plugins/$psubfolder/$lang/help.html") || die "Missing template plugins/$psubfolder/$lang/help.html";
      while (<F>)
      {
         $_ =~ s/<!--\$(.*?)-->/${$1}/g;
         $helptext = $helptext . $_;
      }

    close(F);
    open(F,"$installfolder/templates/system/$lang/header.html") || die "Missing template system/$lang/header.html";
      while (<F>)
      {
        $_ =~ s/<!--\$(.*?)-->/${$1}/g;
        print $_;
      }
    close(F);
  }

#####################################################
# Footer
#####################################################

  sub footer
  {
    open(F,"$installfolder/templates/system/$lang/footer.html") || die "Missing template system/$lang/footer.html";
      while (<F>)
      {
        $_ =~ s/<!--\$(.*?)-->/${$1}/g;
        print $_;
      }
    close(F);
  }
