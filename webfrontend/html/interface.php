 <?php

require_once "loxberry_log.php";
require_once "loxberry_system.php";

$myIP = LBSystem::get_localip();

$params = [	"name" => "Interface PHP",
			"filename" => "$lbplogdir/test.log",
			"append" => 1,
			"addtime" => 1,
			];
$log = LBLog::newLog($params);
	 
	#global $myIP;
	
	// API Url
	$url = 'http://'.$myIP.'/plugins/text2speech/index.php';
	#$url = 'http://'.$myIP.'/plugins/text2speech/index.php?json=1';
	
	// Initiate cURL.
	$ch = curl_init($url);
	
	$text = "Hallo Oliver";
	$greet = "0";
	 
	// populate JSON data.
	$jsonData = array(
		'text' => $text,
		'greet' => "0"
	);
		 
	// Encode the array into JSON.
	$jsonDataEncoded = json_encode($jsonData);
		 
	// Tell cURL that we want to send a POST request.
	curl_setopt($ch, CURLOPT_POST, 1);
	 
	// Attach our encoded JSON string to the POST fields.
	curl_setopt($ch, CURLOPT_POSTFIELDS, $jsonDataEncoded);
	 
	// Set the content type to application/json
	curl_setopt($ch, CURLOPT_HTTPHEADER, array('Content-Type: application/json')); 
	
	// Request response from Call
	curl_setopt($ch, CURLOPT_RETURNTRANSFER, 1);
		 
	// Execute the request
	$result = curl_exec($ch);
	echo '<PRE>';
	print_r(json_decode($result));
	// was the request successful?
	if($result === false)  {
		#LOGGING("Der POST Request war nicht erfolgreich!", 7);
	} else {
		#LOGGING("Der POST Request war erfolgreich!", 7);
	}
	// close cURL
	curl_close($ch);
	return $result;








?>

