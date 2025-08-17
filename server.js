import fs from "fs";
import express from "express";
import cors from "cors";
import dotenv from "dotenv";
import fetchEventSource from "node-fetch-event-source";
import fetch from "node-fetch";

dotenv.config();

const app = express();
app.use(cors());
app.use(express.json());

const API_KEY = process.env.WATSONX_API_KEY;
const DEPLOYMENT_URL =
  "https://us-south.ml.cloud.ibm.com/ml/v4/deployments/dc4f26a3-0d9c-47ec-bb28-cce066b5b82b/ai_service_stream?version=2021-05-01";

async function getToken() {
  const res = await fetch("https://iam.cloud.ibm.com/identity/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: `grant_type=urn:ibm:params:oauth:grant-type:apikey&apikey=${API_KEY}`,
  });
  return (await res.json()).access_token;
}

app.get("/stream", async (req, res) => {
  res.setHeader("Content-Type", "text/event-stream");
  res.setHeader("Cache-Control", "no-cache");
  res.setHeader("Connection", "keep-alive");

  const logStream = fs.createWriteStream("events.log", { flags: "a" });
  const controller = new AbortController();

  req.on("close", () => {
    console.log("❌ Client disconnected");
    controller.abort();
    logStream.end();
    res.end();
  });

  try {
    const token = await getToken();
    const prompt = req.query.prompt || "Hello from Watsonx Orchestrate";

    await fetchEventSource(DEPLOYMENT_URL, {
      fetch,
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body: JSON.stringify({ messages: [{ role: "user", content: prompt }] }),
      signal: controller.signal,

      onmessage(ev) {
        logStream.write(JSON.stringify({ event: ev.event, data: ev.data }) + "\n");

        // Handle EOS (End of Stream) event
        if (ev.event === "eos") {
          console.log("🏁 End of stream event received");
          res.write(`event: stream_end\ndata: {}\n\n`);
          return;
        }

        if (!ev.data || ev.data === "[DONE]") return;

        try {
          const parsed = JSON.parse(ev.data);
          const choice = parsed?.choices?.[0];
          const delta = choice?.delta;
          
          // Console log role information for debugging
          console.log("📨 Event received:", {
            event: ev.event,
            choice_role: choice?.role || "no_choice_role",
            delta_role: delta?.role || "no_delta_role",
            has_content: !!delta?.content,
            has_tool_calls: !!delta?.tool_calls,
            finish_reason: choice?.finish_reason || "no_finish_reason",
            tool_name: choice?.name || "no_tool_name"
          });
          
          // Check for completion/finish events
          if (choice?.finish_reason) {
            console.log("✅ Stream completion event (finish_reason:", choice.finish_reason + ")");
            res.write(`event: completion\ndata: ${JSON.stringify({ finish_reason: choice.finish_reason })}\n\n`);
          }
          // Check if delta role is "tool" - this is tool output
          else if (delta?.role === "tool") {
            console.log("🔧 Sending tool_output event (delta role: tool)");
            res.write(`event: tool_output\ndata: ${JSON.stringify(choice)}\n\n`);
          }
          // Check if delta role is "assistant" and has tool_calls - this is a tool call
          else if (delta?.role === "assistant" && delta?.tool_calls) {
            console.log("⚙️ Sending tool event (delta role: assistant + tool_calls)");
            res.write(`event: tool\ndata: ${JSON.stringify(delta.tool_calls)}\n\n`);
          }
          // Check if delta role is "assistant" and has content - this is assistant output
          else if (delta?.role === "assistant" && delta?.content) {
            console.log("💬 Sending token event (delta role: assistant + content)");
            res.write(`event: token\ndata: ${JSON.stringify(delta.content)}\n\n`);
          }
          // Fallback: check for choice role "tool" (alternative structure)
          else if (choice?.role === "tool") {
            console.log("🔧 Sending tool_output event (choice role: tool)");
            res.write(`event: tool_output\ndata: ${JSON.stringify(choice)}\n\n`);
          }
          else {
            console.log("❓ Unhandled event type - Raw data:", JSON.stringify(parsed, null, 2));
          }
        } catch (err) {
          console.error("Failed to parse SSE data:", err, "Raw data:", ev.data);
        }
      },

      onclose() {
        res.write(`event: done\ndata: {}\n\n`);
        res.end();
        logStream.end();
      },

      onerror(err) {
        console.error("SSE upstream error", err);
        res.write(`event: error\ndata: ${JSON.stringify(err.message)}\n\n`);
        res.end();
        logStream.write(`ERROR: ${err}\n`);
        logStream.end();
      },
    });
  } catch (err) {
    console.error("Backend error:", err);
    res.write(`event: error\ndata: ${JSON.stringify(err.message)}\n\n`);
    res.end();
  }
});

app.listen(3000, () => console.log("✅ Backend running on http://localhost:3000"));
