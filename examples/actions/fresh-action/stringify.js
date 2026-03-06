import fs from "fs";

// read the file, safely escape the contents and wrap in a JSON string
const fileContents = fs.readFileSync("dist/action.js", "utf-8");
const jsonString = JSON.stringify(fileContents);
console.log(jsonString);
