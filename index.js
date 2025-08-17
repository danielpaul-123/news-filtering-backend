
const XMLHttpRequest = require("xmlhttprequest").XMLHttpRequest;
const fs = require("fs");
const API_KEY = "8GhfNz_kkDFCZ2UHdpZOtSOHcC0e5YZqqQRFEt-606fb";
const SCORING_URL = "https://us-south.ml.cloud.ibm.com/ml/v4/deployments/929eb7f9-426e-4df1-b9ac-311fbe0081e5/ai_service_stream?version=2021-05-01";

function getToken(callback) {
	const req = new XMLHttpRequest();
	req.onreadystatechange = function () {
		if (req.readyState === 4) {
			if (req.status === 200) {
				try {
					const token = JSON.parse(req.responseText).access_token;
					callback(null, token);
				} catch (e) {
					callback("Error parsing token response");
				}
			} else {
				callback("Error submitting the request");
			}
		}
	};
	req.open("POST", "https://iam.cloud.ibm.com/identity/token");
	req.setRequestHeader("Content-Type", "application/x-www-form-urlencoded");
	req.setRequestHeader("Accept", "application/json");
	req.send("grant_type=urn:ibm:params:oauth:grant-type:apikey&apikey=" + API_KEY);
}

function scoreMessage(token, payload, callback) {
	const req = new XMLHttpRequest();
	req.onreadystatechange = function () {
		if (req.readyState === 4) {
			// Write the entire raw SSE response to a file
			fs.writeFileSync("sse_response.txt", req.responseText);
			console.log("Raw SSE response written to sse_response.txt");
			if (req.status === 200) {
				callback(null, { message: "SSE response written to file." });
			} else {
				callback("Error submitting scoring request");
			}
		}
	};
	req.open("POST", SCORING_URL);
	req.setRequestHeader("Accept", "application/json");
	req.setRequestHeader("Authorization", "Bearer " + token);
	req.setRequestHeader("Content-Type", "application/json;charset=UTF-8");
	req.send(JSON.stringify(payload));
}

getToken((err, token) => {
	if (err) return console.log(err);
	const payload = { messages: [{ content: "bear spotted in chalakudy. is this true?", role: "user" }] };
	scoreMessage(token, payload, (err, result) => {
		if (err) return console.log(err);
		console.log("Scoring response");
		console.log(JSON.stringify(result, null, 2));
	});
});
