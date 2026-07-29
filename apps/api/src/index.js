const express = require("express");
const cors = require("cors");
require("dotenv").config();

const app = express();
const port = Number(process.env.PORT) || 4000;

app.use(cors({ origin: "http://localhost:3000" }));
app.use(express.json());

app.get("/health", (_request, response) => {
  response.json({ status: "ok" });
});

app.listen(port, () => {
  console.log(`EV SafeCharge API listening on http://localhost:${port}`);
});
