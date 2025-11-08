package Text2SIP::Popup;

use strict;
use warnings;
use utf8;
use JSON qw(encode_json);
use Exporter 'import';
our @EXPORT_OK = qw(flash_popup);


sub _esc {
    my ($s) = @_;
    return '' unless defined $s;
    $s =~ s/&/&amp;/g; $s =~ s/</&lt;/g; $s =~ s/>/&gt;/g;
    $s =~ s/"/&quot;/g; $s =~ s/'/&#39;/g;
    return $s;
}

# Flash Popup

sub flash_popup {
    my (%o) = @_;

    my $title   = defined $o{title}        ? $o{title}        : 'Text2SIP';
    my $reload  = $o{reload} ? 1 : 0;
    my $href    = defined $o{href} ? $o{href} : '';
    my $ms      = defined $o{autoclose_ms} ? int($o{autoclose_ms}) : 1500;

    my $msg_html;
    if ($o{raw_html}) {
        $msg_html = $o{message} // '';
    } else {
        my $m = _esc($o{message} // '');
        $m =~ s/\r?\n/<br\/>/g;
        $msg_html = $m;
    }

    # ---- Icon (optional) ----
    if (defined $o{icon} && length $o{icon}) {
        my $psub = $o{psubfolder} // '';
        my $src =
            ($o{icon} =~ m{^(?:/|https?://)}) ? $o{icon} :
            ($psub ne '')                     ? "/plugins/$psub/$o{icon}" :
                                                $o{icon};

        my $img = '<img src="' . _esc($src)
                . '" style="vertical-align:middle;margin-right:8px;width:24px;height:24px">';
        # IMPORTANT: use **double quotes** for HTML attributes to avoid single quotes!
        $msg_html = '<div style="display:flex;gap:8px;align-items:flex-start;margin:8px 0 4px 0;">'
                  . $img
                  . '<div>'.$msg_html.'</div></div>';
    }

    # ---- Serialize strings safely for JS ----
    my $js_msg   = encode_json($msg_html);  # -> "..."
    my $js_title = encode_json($title);     # -> "..."
    my $js_href  = encode_json($href);      # -> "" if empty

    my $js = <<"JS";
<script>
(function(){
  function openDialog(){
    // Ensure a container exists:
    var \$d = \$('#dialog');
    if (!\$d.length) { \$('body').append('<div id="dialog" style="display:none"></div>'); \$d = \$('#dialog'); }

    // Require jQuery UI; if missing, fall back to alert:
    if (!\$.fn || !\$.fn.dialog) {
      try { console.warn('jQuery UI dialog not found; falling back to alert'); } catch(e){}
      try { alert($js_msg.replace(/<[^>]+>/g,'')); } catch(e){}
      return;
    }

    \$d.html($js_msg).dialog({
      modal: true, title: $js_title, zIndex: 10000, autoOpen: true,
      resizable: true, width: 'auto', height: 'auto', minWidth: 400, minHeight: 230
    });

    setTimeout(function(){
      try { \$d.dialog('close'); } catch(e){}
      if ($reload) { location.reload(true); }
      else {
        var href = $js_href;
        if (href) { location.href = href; }
      }
    }, $ms);
  }
  if (window.jQuery) { jQuery(openDialog); }
  else { document.addEventListener('DOMContentLoaded', openDialog); }
})();
</script>
JS
    return $js;
}

# Confirm Popup 

sub confirm_popup {
    my (%o) = @_;

    my $title   = defined $o{title}        ? $o{title}        : 'Bestätigung';
    my $yeslbl  = defined $o{yes_label}    ? $o{yes_label}    : 'OK';
    my $nolbl   = defined $o{no_label}     ? $o{no_label}     : 'Abbrechen';
    my $href_ok = defined $o{href_yes}     ? $o{href_yes}     : '';  # optional
    my $href_no = defined $o{href_no}      ? $o{href_no}      : '';  # optional
    my $js_ok   = defined $o{on_yes}       ? $o{on_yes}       : '';  # optional: JS-Code (String)
    my $js_no   = defined $o{on_no}        ? $o{on_no}        : '';  # optional
    my $close_on_action = exists $o{close_on_action} ? ($o{close_on_action}?1:0) : 1;

    # Message wie beim flash_popup behandeln
    my $msg_html;
    if ($o{raw_html}) { $msg_html = $o{message} // '' }
    else {
        my $m = _esc($o{message} // ''); $m =~ s/\r?\n/<br\/>/g; $msg_html = $m;
    }

    # Icon (optional) – gleiche Logik wie beim flash_popup
    if (defined $o{icon} && length $o{icon}) {
        my $psub = $o{psubfolder} // '';
        my $src =
            ($o{icon} =~ m{^(?:/|https?://)}) ? $o{icon} :
            ($psub ne '')                     ? "/plugins/$psub/$o{icon}" :
                                                $o{icon};

        my $img = '<img src="' . _esc($src)
                . '" style="vertical-align:middle;margin-right:8px;width:24px;height:24px">';
        $msg_html = '<div style="display:flex;gap:8px;align-items:flex-start;margin:8px 0 4px 0;">'
                  . $img . '<div>'.$msg_html.'</div></div>';
    }

    # JSON-sicher in JS heben (verhindert Quote-Breaks)
    my $js_msg   = encode_json($msg_html);
    my $js_title = encode_json($title);
    my $js_yes   = encode_json($yeslbl);
    my $js_no    = encode_json($nolbl);
    my $js_hrefY = encode_json($href_ok);
    my $js_hrefN = encode_json($href_no);
    my $js_codeY = encode_json($js_ok);  # roher JS-Text als String
    my $js_codeN = encode_json($js_no);

    my $js = <<"JS";
<script>
(function(){
  function openConfirm(){
    var \$d = \$('#dialog');
    if (!\$d.length) { \$('body').append('<div id="dialog" style="display:none"></div>'); \$d = \$('#dialog'); }

    if (!\$.fn || !\$.fn.dialog) {
      var m = $js_msg; try { alert(m.replace(/<[^>]+>/g,'')); } catch(e){}
      return;
    }

    // Aktionen kapseln
    function runAction(codeStr, hrefStr){
      try {
        if (codeStr) { (new Function(codeStr))(); }
      } catch(e) { console && console.error && console.error('confirm on_* error', e); }
      if (hrefStr) { location.href = hrefStr; }
    }

    var btns = {};
    btns[$js_yes] = function(){
      if ($close_on_action) { try { \$d.dialog('close'); } catch(e){} }
      runAction($js_codeY, $js_hrefY);
      if (!$close_on_action) { /* offen lassen */ }
    };
    btns[$js_no] = function(){
      if ($close_on_action) { try { \$d.dialog('close'); } catch(e){} }
      runAction($js_codeN, $js_hrefN);
    };

    \$d.html($js_msg).dialog({
      modal: true, title: $js_title, zIndex: 10000, autoOpen: true,
      resizable: true, width: 'auto', height: 'auto', minWidth: 420, minHeight: 230,
      buttons: btns,
      close: function(){ /* noop */ }
    });
  }

  if (window.jQuery) { jQuery(openConfirm); }
  else { document.addEventListener('DOMContentLoaded', openConfirm); }
})();
</script>
JS
    return $js;
}
1;
