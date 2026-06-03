<?php
	require_once("classes/componentenModel.php");
	require_once("classes/softCompModel.php");
	require_once("classes/socketHandler.php");
	date_default_timezone_set("Europe/Brussels");
	header("Content-type: text/html; charset=utf-8");
	//Set no caching
	header("Expires: Mon, 26 Jul 1997 05:00:00 GMT");
	header("Last-Modified: " . gmdate("D, d M Y H:i:s") . " GMT"); 
	header("Cache-Control: no-store, no-cache, must-revalidate"); 
	header("Cache-Control: post-check=0, pre-check=0", false);
	header("Pragma: no-cache");
	$currLang = "nl";
	$arrStrings = array();
	if (isset($_COOKIE["language"])) {
		$currLang = $_COOKIE["language"];
	}
	$xmlStrings = new DOMDocument();
	$xmlStrings->load("../assets/strings_" . $currLang . ".xml");
	foreach ($xmlStrings->getElementsByTagName('param') as $param) {
		$arrStrings[$param->getAttribute("id")] = $param->nodeValue;
	}
	$socketType = "webservice";
	$dbName = "C:\\Program Files\\ipcom\\ipcom.mdb";
	$dbRadioName = "C:\\Program Files\\ipcom\\RADIO.mdb";
	$dbDmxName = "C:\\Program Files\\ipcom\\DMX.mdb";
	//$dbDmxName = "\\\\10.10.1.9\\ipcom\\DMX.mdb";
	//$dbName = "\\\\10.10.1.9\\ipcom\\ipcom.mdb";
	$ipcomFilePath ="C:\\Program Files\\ipcom\\";
	$playListPath = "c:\\zserver\\mp3\\";
	$songsPath = "c:\\mp3\\";
	$tmpReturn = "";
	if ($_GET["methode"] == "loginCheck") {
		if($_GET["username"] != "" && $_GET["password"] != "") {
			$db = new PDO("odbc:DRIVER={Microsoft Access Driver (*.mdb)}; DBQ=$dbName; Uid=; Pwd=;");
			$tmpSql  = "SELECT * FROM paswoord WHERE gebruikersnaam = '" . $_GET["username"] . "' AND paswoord = '" . $_GET["password"] . "'";
			$result = $db->query($tmpSql);
			$count = 0;
			while ($row = $result->fetch()) {
				$count++;
			}
			if ($count > 0) {
				echo $_GET["username"];
			}
		} else {
			
			$db = new PDO("odbc:DRIVER={Microsoft Access Driver (*.mdb)}; DBQ=$dbName; Uid=; Pwd=;");
			$tmpSql  = "SELECT * FROM paswoord";
			$result = $db->query($tmpSql);
			$count = 0;
			while ($row = $result->fetch()) {
				$count++;
			}
			if(filter_var($_SERVER['SERVER_NAME'], FILTER_VALIDATE_IP) && ((substr($_SERVER['SERVER_NAME'],0,8) == "192.168.") || ($_SERVER['SERVER_NAME'] == "127.0.0.1")  || (substr($_SERVER['SERVER_NAME'],0,6) == "10.10."))) {
				if ($count > 0) {
					echo "local";
				} else {
					echo "noLogin";
				}
			} else {
				if ($count > 0) {
					echo "remote";
				} else {
					echo "noAccess";
				}
			}
		}
	} else if ($_GET["methode"] == "changePassword") {
		$db = new PDO("odbc:DRIVER={Microsoft Access Driver (*.mdb)}; DBQ=$dbName; Uid=; Pwd=;");
		$tmpSql  = "SELECT * FROM paswoord WHERE gebruikersnaam = '" . $_GET["username"] . "' AND paswoord = '" . $_GET["password"] . "'";
		$result = $db->query($tmpSql);
		$count = 0;
		while ($row = $result->fetch()) {
			$count++;
		}
		if ($count > 0) {
			$tmpUpdateSql = "UPDATE paswoord SET paswoord = '" . $_GET["newPassword"] . "' WHERE gebruikersnaam = '" . $_GET["username"] . "'";
			$count = $db->exec($tmpUpdateSql);
			echo $_GET["username"];
		}
	} else if ($_GET["methode"] == "setLoginAccount") {
		$db = new PDO("odbc:DRIVER={Microsoft Access Driver (*.mdb)}; DBQ=$dbName; Uid=; Pwd=;");
		$tmpSql  = "SELECT * FROM paswoord";
		$result = $db->query($tmpSql);
		$count = 0;
		while ($row = $result->fetch()) {
			$count++;
		}
		if ($count <= 0) {
			$tmpInsertSql  = "INSERT INTO paswoord (paswoord, gebruikersnaam) VALUES ('" . $_GET["password"] . "', '" . $_GET["username"] . "')";
			$result = $db->exec($tmpInsertSql);
		}
		echo "ok";
	} else if ($_GET["methode"] == "getGroupList") {
		$db = new PDO("odbc:DRIVER={Microsoft Access Driver (*.mdb)}; DBQ=$dbName; Uid=; Pwd=;");
		$tmpSql  = "SELECT Type, Modula, Adres FROM Componenten WHERE mobileView = 1 ORDER BY Type ASC";
		$result = $db->query($tmpSql);
		$count = 1;
		$dimAmount = 0;
		$tmpCurrType = "";
		$tmpReturn = "";
		$tmpReturn .= '<ul id="leftMenu"><li id="leftMenuSearchField" class="menuSearchField">';
		$tmpReturn .= '<form action="javascript: searchItems_clicked();">';
		$tmpReturn .= '<input id="txt_searchComponents"></input><div id="btn_searchComponents" onclick="searchItems_clicked();">&nbsp;</div>';
		$tmpReturn .= '</form>';
		$tmpReturn .= '</li>';
		$tmpReturn .= '<li id="leftMenuTitleHoofdGr" class="menuTitle" toTranslate="str_headGroups">' . $arrStrings["str_headGroups"] . '</li>';
		// Loop the database results, put them in an array and compose the protocol for the Socket request
		while ($row = $result->fetch()) {
			if ($row["Modula"] != 2 || substr($row["Adres"], 0, 1) == "F") {
				if ($row["Modula"] == 1) {
					$dimAmount++;
				}
				if ($tmpCurrType != $row["Type"]) {
					$tmpReturn .= '<li id="leftMenuItem' . $count . '" class="menuItem" onclick="leftMenuItem_clicked(1,\'' . utf8_encode($row["Type"]) . '\',' . $count . ');">' . utf8_encode($row["Type"]) . '</li>';
					$tmpCurrType = $row["Type"];
					$count++;
				}
			}
		}
		//if ($dimAmount > 0) {
			//$tmpReturn .= '<li id="leftMenuItem' . $count . '" class="menuItem" onclick="leftMenuItem_clicked(3,\'Dimming\',' . $count . ');" toTranslate="str_dimming">' . $arrStrings["str_dimming"] . '</li>';
			//$count++;
		//}
		$tmpSql  = "SELECT DISTINCT Type FROM SoftComp WHERE ID NOT LIKE 'AAV%' ORDER BY Type ASC";
		$result = $db->query($tmpSql);
		while ($row = $result->fetch()) {
			$tmpReturn .= '<li id="leftMenuItem' . $count . '" class="menuItem" onclick="leftMenuItem_clicked(2,\'' . utf8_encode($row["Type"]) . '\',' . $count . ');">' . utf8_encode($row["Type"]) . '</li>';
			$tmpCurrType = $row["Type"];
			$count++;
		}
		$tmpReturn .= '<li id="leftMenuTitleHoofdGr" class="menuTitle" toTranslate="str_regime">' . $arrStrings["str_regime"] . '</li>';
		$tmpSql  = "SELECT * FROM SoftComp WHERE ID LIKE 'AAV%' ORDER BY Omschrijving ASC";
		$result = $db->query($tmpSql);
		while ($row = $result->fetch()) {
			$tmpComponent = new SoftCompModel();
			$tmpComponent->setAttributesDb($row);
			$tmpReturn .= $tmpComponent->generateHtml_LeftMenuItem();
		}
		$tmpReturn .= '</ul>';
		echo $tmpReturn;
	} else if ($_GET["methode"] == "showGroupItems") {
		$db = new PDO("odbc:DRIVER={Microsoft Access Driver (*.mdb)}; DBQ=$dbName; Uid=; Pwd=;");
		$tmpSql  = "SELECT * FROM Componenten WHERE mobileView = 1 AND actief = 1 AND Type = '" . utf8_decode($_GET["groupId"]) . "' ORDER BY Omschrijving ASC";
		$result = $db->query($tmpSql);
		$tmpReturn = "";
		$tmpReturn .= "<div id='content_titleGroup' class='contentTitle'>" . $_GET["groupId"] . "</div>";
		while ($row = $result->fetch()) {
			$tmpComponent = new ComponentenModel();
			$tmpComponent->setAttributesDb($row);
			$tmpComponent->setlangStrings($arrStrings);
			$tmpReturn .= $tmpComponent->generateHtml_itemList();
		}
		echo $tmpReturn;
	} else if ($_GET["methode"] == "showGroupItemsSoft") {
		$db = new PDO("odbc:DRIVER={Microsoft Access Driver (*.mdb)}; DBQ=$dbName; Uid=; Pwd=;");
		$tmpSql  = "SELECT * FROM SoftComp WHERE Type = '" . utf8_decode($_GET["groupId"]) . "' ORDER BY Omschrijving ASC";
		$result = $db->query($tmpSql);
		$tmpReturn = "";
		$tmpReturn .= "<div id='content_titleGroup' class='contentTitle'>" . $_GET["groupId"] . "</div>";
		while ($row = $result->fetch()) {
			$tmpComponent = new SoftCompModel();
			$tmpComponent->setAttributesDb($row);
			$tmpReturn .= $tmpComponent->generateHtml_itemList();
		}
		echo $tmpReturn;
	}  else if ($_GET["methode"] == "showGroupItemsDim") {
		$db = new PDO("odbc:DRIVER={Microsoft Access Driver (*.mdb)}; DBQ=$dbName; Uid=; Pwd=;");
		$tmpSql  = "SELECT * FROM Componenten WHERE mobileView = 1 AND actief = 1 AND Modula = 1";
		$result = $db->query($tmpSql);
		$tmpReturn = "";
		$tmpReturn .= "<div id='content_titleGroup' class='contentTitle'>" . $_GET["groupId"] . "</div>";
		while ($row = $result->fetch()) {
			$tmpComponent = new ComponentenModel();
			$tmpComponent->setAttributesDb($row);
			$tmpComponent->setlangStrings($arrStrings);
			$tmpReturn .= $tmpComponent->generateHtml_itemList();
		}
		echo $tmpReturn;
	} else if ($_GET["methode"] == "searchItems") {
		$db = new PDO("odbc:DRIVER={Microsoft Access Driver (*.mdb)}; DBQ=$dbName; Uid=; Pwd=;");
		$tmpSql  = "SELECT * FROM Componenten WHERE mobileView = 1 AND actief = 1 AND Omschrijving LIKE '%" . utf8_decode($_GET["searchStr"]) . "%' ORDER BY Type, Omschrijving Asc";
		$result = $db->query($tmpSql);
		$count = 0;
		$tmpCurrType = "";
		$tmpReturn = "";
		$tmpReturn .= "<div class='contentTitle' toTranslate='str_searchResults'>" . $arrStrings["str_searchResults"] . "</div>";
		while ($row = $result->fetch()) {
			if ($row["Modula"] != 2 || substr($row["Adres"], 0, 1) == "F") {
				$tmpComponent = new ComponentenModel();
				$tmpComponent->setAttributesDb($row);
				$tmpComponent->setlangStrings($arrStrings);
				if ($tmpCurrType != $tmpComponent->getType()) {
					$tmpReturn .= "<div class='contentSubTitle'>" . $tmpComponent->getType() . "</div>";
					$tmpCurrType = $tmpComponent->getType();
				}
				$tmpReturn .= $tmpComponent->generateHtml_itemList();
				$count++;
			}
		}
		$tmpSql  = "SELECT * FROM SoftComp WHERE ID NOT LIKE 'AAV%' AND Omschrijving LIKE '%" . utf8_decode($_GET["searchStr"]) . "%' ORDER BY Type, Omschrijving Asc";
		$result = $db->query($tmpSql);
		while ($row = $result->fetch()) {
			$tmpComponent = new SoftCompModel();
			$tmpComponent->setAttributesDb($row);
			if ($tmpCurrType != $tmpComponent->getType()) {
				$tmpReturn .= "<div class='contentSubTitle'>" . $tmpComponent->getType() . "</div>";
				$tmpCurrType = $tmpComponent->getType();
			}
			$tmpReturn .= $tmpComponent->generateHtml_itemList();
			$count++;
		}
		if ($count <= 0) {
			$tmpReturn = "<div class='emptyListMsg' toTranslate='str_noResultsFound'>" . $arrStrings["str_noResultsFound"] . "</div>";
		}
		echo $tmpReturn;
	} else if ($_GET["methode"] == "switchRegime") {
		$socketInstance = new SocketHandler();
		$socketInstance->makeConnection($socketType, "tcp", "short");
		$socketInstance->setTimeOutToSocket(0, 500000);
		if ($socketInstance->getSocket() === false) {
    		throw new UnexpectedValueException("Failed to connect: $socketInstance->getErrorMessage()");
		}
		$socketInstance->writeToSocket($_GET["regimeId"]);
		$socketResponse =  $socketInstance->getContentFromSocket();
		$socketInstance->writeToSocket("END");
		$socketInstance->closeSocket();
		echo $socketResponse;
	} else if ($_GET["methode"] == "getStatus") {
		$socketInstance = new SocketHandler();
		$socketInstance->makeConnection($socketType, "tcp", "long");
		$socketInstance->setTimeOutToSocket(0, 500000);
		if ($socketInstance->getSocket() === false) {
    		echo "socket_failed";
		} else {
			$socketInstance->writeToSocket($_GET["reqStr"]);
			$socketResponse = $socketInstance->getContentFromSocket();
			$socketInstance->writeToSocket("END");
			$socketInstance->closeSocket();
			echo $socketResponse;
		}
	} else if ($_GET["methode"] == "getLedStatus") {
		$db = new PDO("odbc:DRIVER={Microsoft Access Driver (*.mdb)}; DBQ=$dbDmxName; Uid=; Pwd=;");
		$arrDmxCh = explode(";", $_GET["reqStr"]);
		$tmpReturn = "";
		for($i=0; $i<count($arrDmxCh); $i++) {
			if ($arrDmxCh[$i] != "") {
				$startIndex = ($arrDmxCh[$i] * 3) - 2;
				$dmxR = 0; $dmxG = 0; $dmxB = 0;
				$tmpReturn .= $arrDmxCh[$i] . "-";
				$tmpSql  = "SELECT * FROM Status WHERE Channel IN (" . $startIndex . "," . ($startIndex + 1) . "," . ($startIndex + 2) . ") ORDER BY Channel Asc";
				$result = $db->query($tmpSql);
				while ($row = $result->fetch()) {
					if ($row["Channel"] == $startIndex) {
						$dmxR = $row["Value"] < 16 ? "0" . dechex($row["Value"]) : dechex($row["Value"]);
					} else if ($row["Channel"] == $startIndex+1) {
						$dmxG = $row["Value"] < 16 ? "0" . dechex($row["Value"]) : dechex($row["Value"]);
					} else if ($row["Channel"] == $startIndex+2) {
						$dmxB = $row["Value"] < 16 ? "0" . dechex($row["Value"]) : dechex($row["Value"]);
					}
				}
				$tmpReturn .= $dmxR . $dmxG . $dmxB . ";";
			}
		}
		echo $tmpReturn;
	} else if ($_GET["methode"] == "setLedColor") {
		$db = new PDO("odbc:DRIVER={Microsoft Access Driver (*.mdb)}; DBQ=$dbDmxName; Uid=; Pwd=;");
		$tmpReturn = "ok";
		$tmpStartPos = 1;
		$tmpCh = ($_GET["dmxCh"] * 3) - 2;
		for ($i=0; $i < 3; $i++) {
			$tmpUpdateSql = "UPDATE Status SET Status.Value = " . hexdec (substr($_GET["dmxColor"], $tmpStartPos, 2)) . " WHERE Channel = " . ($tmpCh + $i);
		 	$count = $db->exec($tmpUpdateSql);
			$tmpStartPos += 2;
		}
		echo $tmpReturn;
	} else if ($_GET["methode"] == "protocolToggleItem") {
		$socketInstance = new SocketHandler();
		$socketInstance->makeConnection($socketType, "tcp", "short");
		$socketInstance->setTimeOutToSocket(0, 500000);
		$strReq = "TGL;" . $_GET["ip"] . "-" . $_GET["ch"];
		if ($socketInstance->getSocket() === false) {
    		throw new UnexpectedValueException("Failed to connect: $socketInstance->getErrorMessage()");
		}
		$socketInstance->writeToSocket($strReq);
		$socketResponse =  $socketInstance->getContentFromSocket();
		$socketInstance->writeToSocket("END");
		$socketInstance->closeSocket();
		echo $socketResponse;
	} else if ($_GET["methode"] == "protocolClearItem") {
		$socketInstance = new SocketHandler();
		$socketInstance->makeConnection($socketType, "tcp", "short");
		$socketInstance->setTimeOutToSocket(0, 500000);
		$strReq = "CLR;" . $_GET["ip"] . "-" . $_GET["ch"];
		if ($socketInstance->getSocket() === false) {
    		throw new UnexpectedValueException("Failed to connect: $socketInstance->getErrorMessage()");
		}
		$socketInstance->writeToSocket($strReq);
		$socketResponse =  $socketInstance->getContentFromSocket();
		$socketInstance->writeToSocket("END");
		$socketInstance->closeSocket();
		echo $socketResponse;
	} else if ($_GET["methode"] == "protocolSetDimValue") {
		$tmpVal = $_GET["dimValue"];
		if ($tmpVal < 10){
			$tmpVal = "0" . $tmpVal;
		}
		$socketInstance = new SocketHandler();
		$socketInstance->makeConnection($socketType, "tcp", "short");
		$socketInstance->setTimeOutToSocket(0, 500000);
		$strReq = "DIM;" . $_GET["ip"] . "-" . $_GET["ch"] . "_" . $tmpVal;
		if ($socketInstance->getSocket() === false) {
    		throw new UnexpectedValueException("Failed to connect: $socketInstance->getErrorMessage()");
		}
		
		$socketInstance->writeToSocket($strReq);
		$socketResponse = $socketInstance->getContentFromSocket();
		$socketInstance->writeToSocket("END");
		$socketInstance->closeSocket();
		echo $socketResponse;
	} else if ($_GET["methode"] == "protocolCallSoftComp") {
		$socketInstance = new SocketHandler();
		$socketInstance->makeConnection($socketType, "tcp", "short");
		$socketInstance->setTimeOutToSocket(0, 500000);
		if ($socketInstance->getSocket() === false) {
    		throw new UnexpectedValueException("Failed to connect: $socketInstance->getErrorMessage()");
		}
		
		$socketInstance->writeToSocket($_GET["reqStr"]);
		$socketResponse =  $socketInstance->getContentFromSocket();
		$socketInstance->writeToSocket("END");
		$socketInstance->closeSocket();
		echo $socketResponse;
	} else if ($_GET["methode"] == "protocolGetCurrRegime") {
		$socketInstance = new SocketHandler();
		$socketInstance->makeConnection($socketType, "tcp", "short");
		$socketInstance->setTimeOutToSocket(0, 500000);
		if ($socketInstance->getSocket() === false) {
    		throw new UnexpectedValueException("Failed to connect: $socketInstance->getErrorMessage()");
		}
		$socketInstance->writeToSocket("AAVX");
		$regimeResponse =  $socketInstance->getContentFromSocket();
		$socketInstance->writeToSocket("END");
		$socketInstance->closeSocket();
		echo substr($regimeResponse, 0, 4);
	} else if ($_GET["methode"] == "showVideoImage") {
		$reqUrl = "";
		$filePath = "";
		$tmpDimensions = "320x240";
		$tmpTest = $tmpNow . "</br>";
		if ($_GET["modula"] == "24") {
			if (intval(substr($_GET["dimensions"], 0, strrpos($_GET["dimensions"], "x"))) > 640 && intval(substr($_GET["dimensions"], strrpos($_GET["dimensions"], "x")+1, strlen($_GET["dimensions"]))) > 480) {
				$tmpDimensions = "640x480";
			}
			$reqUrl = "http://" . $_GET["ip"] . "/enu/camera" . $tmpDimensions . ".jpg";
			$filePath = "assets/video/" . str_replace(".", "_", $_GET["ip"]) . "_" . $tmpDimensions . ".jpg";
			if (intval(substr($_GET["dimensions"], 0, strrpos($_GET["dimensions"], "x"))) < 320 && intval(substr($_GET["dimensions"], strrpos($_GET["dimensions"], "x")+1, strlen($_GET["dimensions"]))) < 240) {
				$tmpWidth = intval(substr($_GET["dimensions"], 0, strrpos($_GET["dimensions"], "x")));
				$tmpDimensions = $tmpWidth . "x" . floor($tmpWidth / 1.33);
			}
		} else if ($_GET["modula"] == "25") {
			if (intval(substr($_GET["dimensions"], 0, strrpos($_GET["dimensions"], "x"))) > 640 && intval(substr($_GET["dimensions"], strrpos($_GET["dimensions"], "x")+1, strlen($_GET["dimensions"]))) > 480) {
				$tmpDimensions = "640x480";
			}
			$reqUrl = "http://" . $_GET["ip"] . "/video.jpg";
			$filePath = "assets/video/" . str_replace(".", "_", $_GET["ip"]) . "_" . $tmpDimensions . ".jpg";
			if (intval(substr($_GET["dimensions"], 0, strrpos($_GET["dimensions"], "x"))) < 320 && intval(substr($_GET["dimensions"], strrpos($_GET["dimensions"], "x")+1, strlen($_GET["dimensions"]))) < 240) {
				$tmpWidth = intval(substr($_GET["dimensions"], 0, strrpos($_GET["dimensions"], "x")));
				$tmpDimensions = $tmpWidth . "x" . floor($tmpWidth / 1.33);
			}
		} else {
			$tmpDimensions = $_GET["dimensions"];
			$reqUrl = "http://" . $_GET["ip"] . "/cgi-bin/viewer/video.jpg?resolution=" . $tmpDimensions;
			//$reqUrl = "http://" . $_GET["ip"] . "/cgi-bin/viewer/video.jpg";
			$filePath = "assets/video/" . str_replace(".", "_", $_GET["ip"]) . "_" . $tmpDimensions . ".jpg";
		}
		if (function_exists('curl_init')){
			$ch = curl_init();
    		curl_setopt($ch, CURLOPT_URL, $reqUrl);
    		curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    		$tmpFile = curl_exec($ch);
    		curl_close($ch);
		} else {
			$tmpFile = @file_get_contents($reqUrl);
		}
		if ($tmpFile === false) {
			echo "error";
		} else {
			file_put_contents("../" . $filePath, $tmpFile);
			echo "<div id='videoPopup'><div class='popUpCloseIcon' onclick='closePopup();'></div><img id='videoContainer_" . str_replace(".", "_", $_GET["ip"]) . "' src='" . $filePath . "?time=" . $_GET["nocache"] . "' style='height:" . substr($tmpDimensions, strrpos($tmpDimensions, "x")+1, strlen($tmpDimensions)) . "px; width: " . substr($tmpDimensions, 0, strrpos($tmpDimensions, "x")) . "px;'/></div>";
		}
	} else if ($_GET["methode"] == "refreshVideoImage") {
		$reqUrl = "";
		$filePath = "";
		$tmpDimensions = "320x240";
		if ($_GET["modula"] == "24") {
			if (intval(substr($_GET["dimensions"], 0, strrpos($_GET["dimensions"], "x"))) > 640 && intval(substr($_GET["dimensions"], strrpos($_GET["dimensions"], "x")+1, strlen($_GET["dimensions"]))) > 480) {
				$tmpDimensions = "640x480";
			}
			$reqUrl = "http://" . $_GET["ip"] . "/enu/camera" . $tmpDimensions . ".jpg";
			$filePath = "assets/video/" . str_replace(".", "_", $_GET["ip"]) . "_" . $tmpDimensions . ".jpg";
		} else if ($_GET["modula"] == "25") {
			if (intval(substr($_GET["dimensions"], 0, strrpos($_GET["dimensions"], "x"))) > 640 && intval(substr($_GET["dimensions"], strrpos($_GET["dimensions"], "x")+1, strlen($_GET["dimensions"]))) > 480) {
				$tmpDimensions = "640x480";
			}
			$reqUrl = "http://" . $_GET["ip"] . "/video.jpg";
			$filePath = "assets/video/" . str_replace(".", "_", $_GET["ip"]) . "_" . $tmpDimensions . ".jpg";
		} else {
			$tmpDimensions = $_GET["dimensions"];
			$reqUrl = "http://" . $_GET["ip"] . "/cgi-bin/viewer/video.jpg?resolution=" . $tmpDimensions;
			//$reqUrl = "http://" . $_GET["ip"] . "/cgi-bin/viewer/video.jpg";
			$filePath = "assets/video/" . str_replace(".", "_", $_GET["ip"]) . "_" . $tmpDimensions . ".jpg";
		}
		if (function_exists('curl_init')){
			$ch = curl_init();
    		curl_setopt($ch, CURLOPT_URL, $reqUrl);
    		curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    		$tmpFile = curl_exec($ch);
    		curl_close($ch);
		} else {
			$tmpFile = @file_get_contents($reqUrl);
		}
		if ($tmpFile === false) {
			echo "error";
		} else {
			file_put_contents("../" . $filePath, $tmpFile);
			echo $filePath . "?time=" . $_GET["nocache"];
		}
	} else if ($_GET["methode"] == "activateTempDeviation") {
		$socketInstance = new SocketHandler();
		$socketInstance->makeConnection($socketType, "tcp", "short");
		$socketInstance->setTimeOutToSocket(0, 500000);
		$tmpReqStr = "TAF;" . $_GET["ip"] . "-" . $_GET["address"] . "_" . $_GET["reqTemp"] . "_" . $_GET["reqTime"];
		if ($socketInstance->getSocket() === false) {
    		throw new UnexpectedValueException("Failed to connect: $socketInstance->getErrorMessage()");
		}
		$socketInstance->writeToSocket($tmpReqStr);
		$socketResponse =  $socketInstance->getContentFromSocket();
		$socketInstance->writeToSocket("END");
		$socketInstance->closeSocket();
		echo "INF;" . $_GET["ip"] . "-" . $_GET["address"];
	} else if ($_GET["methode"] == "deleteTempDeviation") {
		$socketInstance = new SocketHandler();
		$socketInstance->makeConnection($socketType, "tcp", "short");
		$socketInstance->setTimeOutToSocket(0, 500000);
		$tmpReqStr = "TAN;" . $_GET["ip"] . "-" . $_GET["address"];
		if ($socketInstance->getSocket() === false) {
    		throw new UnexpectedValueException("Failed to connect: $socketInstance->getErrorMessage()");
		}
		
		$socketInstance->writeToSocket($tmpReqStr);
		$socketResponse =  $socketInstance->getContentFromSocket();
		$socketInstance->writeToSocket("END");
		$socketInstance->closeSocket();
		echo "INF;" . $_GET["ip"] . "-" . $_GET["address"];
	} else if ($_GET["methode"] == "loadAudioPlayer") {
		$tmpIpBarix = $_GET["ip"];
		if ($_GET["modula"] == 3) {
			$db = new PDO("odbc:DRIVER={Microsoft Access Driver (*.mdb)}; DBQ=$dbName; Uid=; Pwd=;");
			$tmpSql  = "SELECT * FROM Audioswitch WHERE IP = '" . $_GET["ip"] . "'";
			$result = $db->query($tmpSql);
			if ($row = $result->fetch()) {
				$tmpIpBarix = $row["IPSource"];
			}
		}
		$tmpReturn = "";
		$tmpReturn .= '<div id="audioPlayer">';
		$tmpReturn .= '<div id="audioPlayerIpBarix" style="display: none;">' . $tmpIpBarix . '</div>';
		$tmpReturn .= '<div id="audioPlayerHeader">';
		$tmpReturn .= '<div id="audioPlayerBack" onclick="navBackToList();"></div>';
		$tmpReturn .= urldecode($_GET["descr"]) . '</div>';
		$tmpReturn .= '<div class="audioPlayerlcd">';
		$tmpReturn .= '<div id="audioPlayerPowerButton" onclick="toggleAudioPlayerPower(\'' . $_GET["ip"] . '\', \'' . $_GET["ch"] . '\');"></div>';
		$tmpReturn .= '<div style="float: left; margin: 0px 0px 0px 5px;">';
		$tmpReturn .= '<div class="audioPlayerVolDownIcon" onclick="navigateAudioPlayerValue(\'Vol\', \'Down\');" isActive="no"></div>';
		$tmpReturn .= '<div id="audioPlayerVolDisplay">';
		$tmpReturn .= '<div id="audioPlayerVol10" class="audioPlayerVolDigital"></div>';
		$tmpReturn .= '<div id="audioPlayerVol1" class="audioPlayerVolDigital"></div>';
		$tmpReturn .= '</div>';
		$tmpReturn .= '<div class="audioPlayerVolUpIcon" onclick="navigateAudioPlayerValue(\'Vol\', \'Up\');" isActive="no"></div>';
		$tmpReturn .= '<div class="audioPlayerLcdValContainer">';
		$tmpReturn .= '<div id="audioPlayerBassVal" class="audioPlayerLcdVal">' . str_replace ("%%value%%", "", $arrStrings["str_bassLcd"]) . '</div>';
		$tmpReturn .= '<div id="audioPlayerTrebVal" class="audioPlayerLcdVal">' . str_replace ("%%value%%", "", $arrStrings["str_trebleLcd"]) . '</div>';
		$tmpReturn .= '</div>';
		$tmpReturn .= '<div id="audioPlayerLcdTrack"></div>';
		$tmpReturn .= '<div id="audioPlayerLcdSource"></div>';
		$tmpReturn .= '</div>';
		$tmpReturn .= '</div>';
		$tmpReturn .= '<div class="audioPlayerbuttons">';
		$tmpReturn .= '<div class="audioPlayerSliderContainer">';
		$tmpReturn .= '<div class="audioPlayerSliderLbl" toTranslate="str_bass">' . $arrStrings["str_bass"] . '</div>';
		$tmpReturn .= '<div class="audioPlayerSliderDownIcon" onclick="navigateAudioPlayerValue(\'Bass\', \'Down\');"></div>';
		$tmpReturn .= "<form id=\"frm_audioPlayerBassSlider\"><div id=\"audioPlayerBassSlider\" class=\"noUiSlider\"></div></form>";
		$tmpReturn .= '<div class="audioPlayerSliderUpIcon" onclick="navigateAudioPlayerValue(\'Bass\', \'Up\');"></div>';
		$tmpReturn .= '</div>';
		$tmpReturn .= '<div class="audioPlayerSliderContainer">';
		$tmpReturn .= '<div class="audioPlayerSliderLbl" toTranslate="str_treble">' . $arrStrings["str_treble"] . '</div>';
		$tmpReturn .= '<div class="audioPlayerSliderDownIcon" onclick="navigateAudioPlayerValue(\'Treb\', \'Down\');"></div>';
		$tmpReturn .= "<form id=\"frm_audioPlayerTrebSlider\"><div id=\"audioPlayerTrebSlider\" class=\"noUiSlider\"></div></form>";
		$tmpReturn .= '<div class="audioPlayerSliderUpIcon" onclick="navigateAudioPlayerValue(\'Treb\', \'Up\');"></div>';
		$tmpReturn .= '</div>';
		
		$tmpReturn .= '</div>';
		$tmpReturn .= '<div class="audioPlayerPlaylistContainer">';
		$tmpReturn .= '<ul id="audioPlayerSourceList" class="audioPlayerPlaylist">';
		$filePlayList = fopen($ipcomFilePath . "playlist.txt", "r");
		$count = 1;
		while (!feof($filePlayList)) {
			$line_of_text = fgets($filePlayList);
			if ($line_of_text != "") {
				//delete return or newline
				$line_of_text = ereg_replace("[\r\n]", '', $line_of_text);
				$tmpLabel = substr($line_of_text, 4);
				$tmpLabel = substr($tmpLabel, 0, strpos($tmpLabel, "."));
				$tmpReturn .= '<li id="audioPlayerSourceListItem_' . $count . '" onclick="playListItem_clicked(' . $count . ');" listValue="' . $line_of_text . '">' . $tmpLabel . '</li>';
				$count++;
			}
		}
		$tmpReturn .= '</ul>';
		$tmpReturn .= '</div>';
		fclose($filePlayList);
		$tmpReturn .= '<div id="audioPlayerSongListContainer"/>';
		$tmpReturn .= '</div>';
		echo $tmpReturn;
	} else if ($_GET["methode"] == "getAudioPlayerStatus") {
		$reqStr = "INF;" . $_GET["ipBarix"];
		if ($_GET["ip"] != $_GET["ipBarix"]) {
			$reqStr .= ";" . $_GET["ip"] . "-" . $_GET["ch"];
		}
		$socketInstance = new SocketHandler();
		$socketInstance->makeConnection($socketType, "tcp", "long");
		$socketInstance->setTimeOutToSocket(0, 500000);
		if ($socketInstance->getSocket() === false) {
    		throw new UnexpectedValueException("Failed to connect: $socketInstance->getErrorMessage()");
		}
		
		$socketInstance->writeToSocket($reqStr);
		$socketResponse =  $socketInstance->getContentFromSocket();
		$socketInstance->writeToSocket("END");
		$socketInstance->closeSocket();
		echo $socketResponse;
	} else if ($_GET["methode"] == "audioPlayerLoadPlayList") {
		$tmpReturn = '';
		$tmpReturn .= '<div class="audioPlayerPlaylistContainer">';
		$tmpReturn .= '<ul id="audioPlayerSongsList" class="audioPlayerPlaylist">';
		$fileSongList = fopen($playListPath . substr($_GET["playList"], strpos($_GET["playList"], ".")+1), "r");
		$count = 1;
		while (!feof($fileSongList)) {
			$line_of_text = fgets($fileSongList);
			if ($line_of_text != "") {
				//delete return or newline
				$tmpLabel = ""; $tmpListValue = "";
				$line_of_text = ereg_replace("[\r\n]", '', $line_of_text);
				if (strpos($line_of_text, $songsPath) === FALSE) {
					$db = new PDO("odbc:DRIVER={Microsoft Access Driver (*.mdb)}; DBQ=$dbRadioName; Uid=; Pwd=;");
					$tmpSql  = "SELECT * FROM Radio WHERE pat = '" . $line_of_text . "'";
					$result = $db->query($tmpSql);
					$tmpListValue = str_replace("http://", "", $line_of_text);
					$tmpListValue = str_replace(".mp3", "", $tmpListValue);
					$tmpListValue = substr($tmpListValue, strpos($tmpListValue, "/")+1);
					while ($row = $result->fetch()) {
						$tmpLabel = utf8_encode($row["Naam"]);
					}
					if ($tmpLabel == "") {
						$tmpLabel = $tmpListValue;
					}
				} else {
					$tmpListValue = str_replace($songsPath, "", $line_of_text);
					$tmpListValue = str_replace(".mp3", "", $tmpListValue);
					$tmpListValue = substr($tmpListValue, strpos($tmpListValue, "\\")+1);
					$tmpLabel = $tmpListValue;
				}
				if (($_GET["song"] == "" && $count == 1) || $_GET["song"] == $tmpListValue) {
					$tmpReturn .= '<li id="audioPlayerSongListItem_' . $count . '" class="active" onclick="songListItem_clicked(' . $count . ');" listValue="' . $tmpListValue . '">' . $tmpLabel . '</li>';
				} else {
					$tmpReturn .= '<li id="audioPlayerSongListItem_' . $count . '" onclick="songListItem_clicked(' . $count . ');" listValue="' . $tmpListValue . '">' . $tmpLabel . '</li>';
				}
				$count++;
			}
		}
		$tmpReturn .= '</ul>';
		$tmpReturn .= '</div>';
		fclose($fileSongList);
		echo $tmpReturn;
	} else if ($_GET["methode"] == "audioPlayerPower") {
		$socketInstance = new SocketHandler();
		$socketInstance->makeConnection($socketType, "tcp", "short");
		$socketInstance->setTimeOutToSocket(0, 500000);
		if ($socketInstance->getSocket() === false) {
    		throw new UnexpectedValueException("Failed to connect: $socketInstance->getErrorMessage()");
		}
		
		$socketInstance->writeToSocket($_GET["reqStr"]);
		$socketResponse =  $socketInstance->getContentFromSocket();
		$socketInstance->writeToSocket("END");
		$socketInstance->closeSocket();
		
		echo $socketResponse;
	} else if ($_GET["methode"] == "audioPlayerSetValue") {
		$reqStr = "SET;";
		if ($_GET["type"] == "Vol") {
			$reqStr .= $_GET["ip"] . "-20_" . $_GET["volVal"];
		} else if ($_GET["type"] == "Bass") {
			$reqStr .= $_GET["ip"] . "-23_" . ($_GET["volVal"]+100);
		} else if ($_GET["type"] == "Treb") {
			$reqStr .= $_GET["ip"] . "-22_" . ($_GET["volVal"]+100);
		}
		$socketInstance = new SocketHandler();
		$socketInstance->makeConnection($socketType, "tcp", "short");
		$socketInstance->setTimeOutToSocket(0, 500000);
		if ($socketInstance->getSocket() === false) {
    		throw new UnexpectedValueException("Failed to connect: $socketInstance->getErrorMessage()");
		}
		$socketResponse = "";
		if ($reqStr != "SET;") {
			$socketInstance->writeToSocket($reqStr);
			$socketResponse =  $socketInstance->getContentFromSocket();
			$socketInstance->writeToSocket("END");
			$socketInstance->closeSocket();
		}
		echo $socketResponse;
	} else if ($_GET["methode"] == "audioPlayerNavigateValue") {
		$reqStr = "SET;";
		if ($_GET["direction"] == "Up") {
			if ($_GET["type"] == "Vol") {
				$reqStr .= $_GET["ip"] . "-03_000";
			} else if ($_GET["type"] == "Bass") {
				$reqStr .= $_GET["ip"] . "-09_000";
			} else if ($_GET["type"] == "Treb") {
				$reqStr .= $_GET["ip"] . "-07_000";
			}
		} else {
			if ($_GET["type"] == "Vol") {
				$reqStr .= $_GET["ip"] . "-04_000";
			} else if ($_GET["type"] == "Bass") {
				$reqStr .= $_GET["ip"] . "-10_000";
			} else if ($_GET["type"] == "Treb") {
				$reqStr .= $_GET["ip"] . "-08_000";
			}	
		}
		$socketInstance = new SocketHandler();
		$socketInstance->makeConnection($socketType, "tcp", "short");
		$socketInstance->setTimeOutToSocket(0, 500000);
		if ($socketInstance->getSocket() === false) {
    		throw new UnexpectedValueException("Failed to connect: $socketInstance->getErrorMessage()");
		}
		
		$socketResponse = "";
		if ($reqStr != "SET;") {
			$socketInstance->writeToSocket($reqStr);
			$socketResponse =  $socketInstance->getContentFromSocket();
			$socketInstance->writeToSocket("END");
			$socketInstance->closeSocket();
		}
		echo $socketResponse;
	} else if ($_GET["methode"] == "protocolAudioPlayerLoadPlaylist") {
		$reqStr = "SET;" . $_GET["ip"] . "-21_" . $_GET["playList"];
		$socketInstance = new SocketHandler();
		$socketInstance->makeConnection($socketType, "tcp", "short");
		$socketInstance->setTimeOutToSocket(0, 500000);
		if ($socketInstance->getSocket() === false) {
    		throw new UnexpectedValueException("Failed to connect: $socketInstance->getErrorMessage()");
		}
		
		$socketInstance->writeToSocket($reqStr);
		$socketResponse =  $socketInstance->getContentFromSocket();
		$socketInstance->writeToSocket("END");
		$socketInstance->closeSocket();
		echo $reqStr;
	} else if ($_GET["methode"] == "protocolAudioPlayerLoadSong") {
		$reqStr = "SET;" . $_GET["ip"] . "-33_" . $_GET["song"];
		$socketInstance = new SocketHandler();
		$socketInstance->makeConnection($socketType, "tcp", "short");
		$socketInstance->setTimeOutToSocket(0, 500000);
		if ($socketInstance->getSocket() === false) {
    		throw new UnexpectedValueException("Failed to connect: $socketInstance->getErrorMessage()");
		}
		
		$socketInstance->writeToSocket($reqStr);
		$socketResponse =  $socketInstance->getContentFromSocket();
		$socketInstance->writeToSocket("END");
		$socketInstance->closeSocket();
		echo $reqStr;
	}
?>
