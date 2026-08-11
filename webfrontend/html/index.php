<?php
// LoxBerry Text2SIP-Plugin
// Christian Woerstenfeld - git@loxberry.woerstenfeld.de
// 12.02.2019 19:04:57
// Updated 2025-11-28: main make_call is forwarded to index.cgi (do=makecall)

// Configuration parameters
error_reporting(~E_STRICT & ~E_NOTICE);     // Keine Strict / Notice Fehler reporten 
ini_set("display_errors", false);           // Fehler nicht direkt via PHP ausgeben

require_once "loxberry_system.php";
require_once "loxberry_log.php";

$plugindata = LBSystem::plugindata();

ini_set("log_errors", 1);

// Pfade / Basisvariablen
$psubdir       = array_pop(array_filter(explode('/', pathinfo($_SERVER["SCRIPT_FILENAME"], PATHINFO_DIRNAME))));
$mydir         = pathinfo($_SERVER["SCRIPT_FILENAME"], PATHINFO_DIRNAME);
$pluginlogfile = $lbplogdir . "/Text2SIP.log";
$sipcmdlogfile = $lbplogdir . "/Text2SIP.log";

$plugindatadir      = $mydir . "/../../../../data/plugins/$psubdir/wav";
$plugincfgfile      = $mydir . "/../../../../config/plugins/$psubdir/Text2SIP.cfg";
$pluginlanguagefile = $mydir . "/../../../../templates/plugins/$psubdir/de/language.dat";

$pico2wave     = "/usr/bin/pico2wave";
$sox           = "/usr/bin/sox";
$sipcmd        = $mydir . "/../../../../webfrontend/htmlauth/plugins/$psubdir/bin/sipcmd";
$option_o      = ""; // Heavy sipcmd Debug (legacy)

$plugin_phrase_array = @parse_ini_file("$pluginlanguagefile");
$plugin_cfg_array    = @parse_ini_file("$plugincfgfile");

$DEBUG_USE  = isset($plugin_cfg_array['DEBUG_USE'])   ? $plugin_cfg_array['DEBUG_USE']   : 'off';
$PLUGIN_USE = isset($plugin_cfg_array['PLUGIN_USE'])  ? $plugin_cfg_array['PLUGIN_USE']  : 'off';

// DEBUG_USE normalisieren -> 'on' / 'off'
if (is_bool($DEBUG_USE)) {
    $DEBUG_USE = $DEBUG_USE ? 'on' : 'off';
} else {
    $DEBUG_USE = strtolower(trim((string)$DEBUG_USE));
    $DEBUG_USE = in_array($DEBUG_USE, ['on','1','true','yes'], true) ? 'on' : 'off';
}

// PLUGIN_USE normalisieren -> 'on' / 'off'
if (is_bool($PLUGIN_USE)) {
    $PLUGIN_USE = $PLUGIN_USE ? 'on' : 'off';
} else {
    $PLUGIN_USE = strtolower(trim((string)$PLUGIN_USE));
    $PLUGIN_USE = in_array($PLUGIN_USE, ['on','1','true','yes'], true) ? 'on' : 'off';
}

if ($PLUGIN_USE !== 'on') {
    $msg = $plugin_phrase_array['ERROR0003'] ?? ' Text2SIP plugin is disabled.';
    die($msg);
}

// -------------------------------------------------------------
// Logging-Helfer (legacy Style aus Originalindex.php)
// -------------------------------------------------------------
function debug($message = "", $parameter = "", $loglevel = 7)
{
    global $L, $plugindata, $DEBUG_USE, $plugin_phrase_array, $lbplogdir, $pluginlogfile;

    if ($DEBUG_USE === 'on') {
        $loglevel = 7;
    }

    if (isset($plugin_phrase_array[$message])) {
        $message = $plugin_phrase_array[$message];
    }
    $message = $message . "" . $parameter;

    $current_level = isset($plugindata['PLUGINDB_LOGLEVEL']) ? intval($plugindata['PLUGINDB_LOGLEVEL']) : 7;

    if ($current_level >= $loglevel) {
        switch ($loglevel) {
            case 1:
                error_log(strftime("%A") . " <ALERT> PHP: " . $message, 3, $pluginlogfile);
                break;
            case 2:
                error_log(strftime("%A") . " <CRITICAL> PHP: " . $message, 3, $pluginlogfile);
                break;
            case 3:
                error_log(strftime("%A") . " <ERROR> PHP: " . $message, 3, $pluginlogfile);
                break;
            case 4:
                error_log(strftime("%A") . " <WARNING> PHP: " . $message, 3, $pluginlogfile);
                break;
            case 5:
                error_log(strftime("%A") . " <OK> PHP: " . $message, 3, $pluginlogfile);
                break;
            case 6:
                error_log(strftime("%A") . " <INFO> PHP: " . $message, 3, $pluginlogfile);
                break;
            case 7:
            default:
                error_log(strftime("%A") . " PHP: " . $message, 3, $pluginlogfile);
                break;
        }
    }
    return;
}

// -------------------------------------------------------------
// Defaults f�r inexistent variables
// -------------------------------------------------------------
if (!isset($_REQUEST["mode"])) {
    $_REQUEST["mode"] = 'normal';
}

// -------------------------------------------------------------
// Logfile Download (called from index.cgi) 
// -------------------------------------------------------------
if ($_REQUEST["mode"] == "download_logfile") {

    if (file_exists($pluginlogfile)) {
        error_log(date('Y-m-d H:i:s ') . "[LOG] Download logfile\n", 3, $pluginlogfile);
        header('Content-Description: File Transfer');
        header('Content-Type: text/plain');
        header('Content-Disposition: attachment; filename="' . basename($pluginlogfile) . '"');
        header('Expires: 0');
        header('Cache-Control: must-revalidate');
        header('Pragma: public');
        header('Content-Length: ' . filesize($pluginlogfile));
        readfile($pluginlogfile);
    } else {
        error_log(date('Y-m-d H:i:s ') . "Error reading logfile!\n", 3, $pluginlogfile);
        die("Error reading logfile.");
    }
    exit;
}

// -------------------------------------------------------------
// Logfile leeren (called from index.cgi) 
// -------------------------------------------------------------
elseif ($_REQUEST["mode"] == "empty_logfile") {

    if (file_exists($pluginlogfile)) {
        $f = @fopen("$pluginlogfile", "r+");
        if ($f !== false) {
            ftruncate($f, 0);
            fclose($f);
            debug("Logfile content deleted", "", 6);
            $result = "\n<img src='/plugins/$psubdir/Text2SIP_ok.png'>";
        } else {
            debug("Logfile content not deleted due to problems doing it.", "", 3);
            $result = "\n<img src='/plugins/$psubdir/Text2SIP_fail.png'>";
        }
    } else {
        $result = "\n<img src='/plugins/$psubdir/Text2SIP_fail.png'>";
    }
}

// -------------------------------------------------------------
// Hauptanwendung: make_call
// ? Weiterleitung an index.cgi (do=makecall) + tts-Support
//    Beispiel-Aufruf:
//    /plugins/text2sip/index.php?mode=make_call&vg=1&tts=Irgend%20ein%20Text
// -------------------------------------------------------------
else if ($_REQUEST["mode"] == "make_call")
{
    // VG aus Request holen
    $vg = isset($_REQUEST["vg"]) ? intval($_REQUEST["vg"]) : 0;

    // Optional: TTS-Text (wird sp�ter an index.cgi durchgereicht)
    $tts = isset($_REQUEST["tts"]) ? $_REQUEST["tts"] : '';

    // Optional: DEBUG_USE aus Request (z.B. f�r Test aus der UI)
    $debug_use = isset($_REQUEST["DEBUG_USE"]) ? $_REQUEST["DEBUG_USE"] : '';

    error_log(
        date('Y-m-d H:i:s ') .
        " index.php: Incoming VG ID: $vg, tts='" . $tts . "'\n",
        3,
        $pluginlogfile
    );

    if ($vg <= 0) {
        error_log(
            date('Y-m-d H:i:s ') .
            " index.php: Invalid VG ID\n",
            3,
            $pluginlogfile
        );
        header('Content-Type: text/plain; charset=utf-8');
        echo ":(\n";
        exit;
    }

    // index.cgi liegt im HTMLAUTH-Bereich
    // $lbphtmlauthdir z.B.:
    //   REPLACELBHOMEDIR/webfrontend/htmlauth/plugins/text2sip
    $cgipath = $lbphtmlauthdir . "/index.cgi";

    if (!is_file($cgipath) || !is_readable($cgipath)) {
        error_log(
            date('Y-m-d H:i:s ') .
            " index.php: index.cgi not found or unreadable at $cgipath\n",
            3,
            $pluginlogfile
        );
        header('Content-Type: text/plain; charset=utf-8');
        echo ":(\n";
        exit;
    }

    // ---------------------------------------------------------
    // CGI-Environment f�r index.cgi simulieren
    // Query-String aufbauen:
    //   - Pflicht: do=makecall & vg=X
    //   - Optional: tts=... (URL-encoded)
    //   - Optional: DEBUG_USE=on
    // ---------------------------------------------------------
    $qs = 'do=makecall&vg=' . $vg;

    if ($tts !== '') {
        // URL-encoden, damit Leerzeichen/Umlaute sauber ankommen
        $qs .= '&tts=' . rawurlencode($tts);
    }

    if ($debug_use === 'on') {
        $qs .= '&DEBUG_USE=on';
    }

    // Shell-Kommando zusammenbauen:
    // - QUERY_STRING wird als Environment-Variable gesetzt
    // - index.cgi wird mit /usr/bin/perl gestartet
    $cmd = 'REQUEST_METHOD=GET GATEWAY_INTERFACE=CGI/1.1 ' .
           'QUERY_STRING=' . escapeshellarg($qs) . ' ' .
           '/usr/bin/perl ' . escapeshellarg($cgipath) .
           ' 2>>' . escapeshellarg($pluginlogfile);

    $output = [];
    $retval = 0;
    exec($cmd, $output, $retval);

    // Erste 200 Zeichen von STDOUT ins Log � zur Diagnose
    $short_out = substr(implode("\n", $output), 0, 200);
    error_log(
        date('Y-m-d H:i:s ') .
        " index.php: index.cgi called, rc=$retval, stdout=" .
        str_replace("\n", "\\n", $short_out) . "\n",
        3,
        $pluginlogfile
    );

    // Nach au�en � wie gewohnt � nur Smiley
    header('Content-Type: text/plain; charset=utf-8');
    echo ($retval === 0) ? ":o)\n" : ":(\n";
    exit;
}
// -------------------------------------------------------------
// Default / unbekannte Modes
// -------------------------------------------------------------
else {
    $result = "?! :o(";
}

header('Content-Type: text/plain; charset=utf-8');
echo "$result";
exit;
