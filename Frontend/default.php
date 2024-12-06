<?php

defined('_JEXEC') or die;
?>

<div id="assistant">
   <style>
  #chat-container {
    height: 100%;
    position: fixed;
    right: 0px;
    bottom: 0px;
    width: 200px;
    height: 56px;
    display: flex;
    flex-direction: column;
    column-gap: 0px;
    justify-content: space-between;
    border-radius: 5px;
    background-color: rgb(247, 247, 247);
    transition: height 0.5s ease, width 0.5s ease;
    z-index: 1050;
  }

  .inactive-el {
    pointer-events: none;
  }

  /* Confirmation Screen */
  #confirmation-screen {
    position: absolute;
    flex-direction: column;
    background-color: hsl(0, 0%, 90%);
    border-radius: 10px;
    box-shadow: 0px 0px 15px rgba(0, 0, 0, 0.342);
    width: 50%;
    margin: auto;
    bottom: 50%;
    left: 50%;
    transform: translate(-50%, 25%);
  }

  #confirm-header {
    background-color: rgb(61, 64, 91);
    color: white;
    padding: 3%;
  }

  #confirmation-screen p {
    margin: 0;
    padding: 2% 3%;
  }

  #button-div {
    display: flex;
    flex-direction: row;
    justify-content: space-evenly;
    margin-top: 8px;
    padding-bottom: 5%;
  }

  #button-div button {
    padding: 2%;
    width: 45px;
    border-radius: 4px;
    border-width: 1px;
    border-style: solid;
    box-shadow: 2px 3px 3px rgba(0, 0, 0, 0.116);
  }

  #confirm-yes {
    border-color: #1090a1;
    color: rgb(255, 255, 255);
    background-color: #1090a1;
    transition: all 0.125s ease;
  }

  #confirm-yes:hover {
    border-color: #0f8392;
    background-color: #0f8392;
  }

  #confirm-no {
    border-color: #1090a1;
    color: #1090a1;
    background-color: rgba(255, 255, 255, 0);
    transition: all 0.125s ease;
  }

  #confirm-no:hover {
    border-color: #0c7280;
    color: #0c7280;
  }

  #button-div button:hover {
    cursor: pointer;
  }

  /* Header */
  #header-view {
    display: flex;
    flex-direction: row;
    justify-content: space-between;
    padding: 0 8px 0 8px;
    background-color: rgb(61, 64, 91);
    border-radius: 5px 5px 0 0;
    cursor: pointer;
    transition: background-color 0.1s ease;
  }

  #header-view:hover {
    background-color: rgb(47, 50, 74);
  }

  #left-header {
    display: flex;
    column-gap: 5px;
  }

  #header-icon {
    flex: 0 0 20px;
    border: 0px;
    border-radius: 5px;
    height: 20px;
    color: white;
    margin: auto 9px auto;
    transition: background-color 0.125s ease;
    transition: opacity 500ms, visibility 500ms;
  }

  .chat-icon-container {
    width: 40px;
    height: 40px;
    margin: 8px 5px;
    object-fit: cover;
  }

  .chat-icon {
    width: 100%;
    height: 100%;
    border-radius: 50%;
    background-color: rgb(218, 211, 207);
  }

  .default-text {
    font-family: Arial, Helvetica, sans-serif;
    font-weight: 300;
    height: auto;
    margin: auto 0 auto;
  }

  #bot-name {
    color: white;
    margin: auto 8px auto 0;
    font-size: 16px;
  }

  /* Chat */
  #disclaimer {
    color: gray;
    margin: 0;
    text-align: center;
    padding-bottom: 4px;
  }

  #message-container {
    padding: 0px 15px 0 10px;
    overflow-x: hidden;
  }

  #chat-wrapper {
    display: flex;
    flex-direction: column;
    justify-content: start;
    height: 100%;
    padding: 5px 0 5px 0;
    overflow-y: auto;
  }

  /* Bot Chat */
  .bot-container {
    width: 100%;
    margin-top: 10px;
    display: flex;
    flex-direction: row;
    align-items: flex-start;
  }

  .bot-message {
    height: auto;
    width: auto;
    display: flex;
    flex-direction: column;
    margin-right: 20px;
  }

  .fine-bot-name {
    color: rgb(175, 175, 175);
    width: auto;
    font-size: 12px;
  }

  .bot-text {
    padding: 10px 10px 10px 10px;
    border-radius: 7px;
    background-color: #e6ebf1;
    width: 100%;
    max-width: 365px;
    word-wrap: break-word;
    overflow-wrap: break-word;
    white-space: pre-line;
    min-height: 18.4px;
  }

  .bot-text * {
    margin: 0;
  }

  .copy-button {
    display: inline-block;
    position: relative;
    height: 15px;
    color: #999999;
    width: 15px;
    margin: auto 6px auto 6px;
    transition: color 125ms;
  }

  .copy-button:hover {
    cursor: pointer;
    color: #adadad;
  }

  .copy-button:active {
    color: #838383;
  }

  .copy-message {
    position: absolute;
    visibility: hidden;
    opacity: 0;
    bottom: 100%;
    left: 50%;
    font-size: 12px;
    color: rgba(0, 0, 0, 0.74);
    transform: translate(-50%, -50%);
    background-color: rgba(243, 243, 243, 0.877);
    border-radius: 3px;
    padding: 2px;
    transition: opacity 50ms, visibility 50ms;
  }

  .copy-message:hover {
    cursor: default;
  }

  /* User Chat */
  .user-container {
    margin-top: 10px;
    display: flex;
    flex-direction: row;
    justify-content: end;
    margin-left: 70px;
  }

  .user-text {
    padding: 10px;
    border-radius: 7px;
    color: white;
    background-color: #0f8c9d;
    width: auto;
    max-width: 365px;
    word-wrap: break-word;
    overflow-wrap: break-word;
    white-space: pre-line;
    min-height: 18.4px;
  }

  /* Reset Message */
  #reset-message {
    color: rgb(187, 187, 187);
    display: flex;
    justify-content: center;
  }

  /* User Answer */
  #clear-chat-button {
    flex: 0 0 20px;
    border: 0px;
    border-radius: 5px;
    height: 20px;
    padding: 10px;
    margin: auto;
    background-color: rgb(240, 240, 240);
    transition: background-color 0.125s ease;
  }

  #clear-chat-button:hover {
    background-color: rgb(228, 228, 228);
    cursor: pointer;
  }

  #answer-view {
    display: flex;
    column-gap: 5px;
    justify-content: stretch;
    padding: 5px 15px 15px 15px;
  }

  #user-answer {
    border: 1px solid rgb(221, 221, 221);
    border-radius: 5px;
    padding: 10px;
    flex: 1 1 auto;
    font-size: 15px;
    flex-shrink: 1000;
  }

  #user-answer:focus {
    outline: none;
  }

  #submit-btn {
    height: auto;
    flex: 0 0 50px;
    background-color: #0f8c9d;
    color: white;
    border: 1px solid rgb(138, 138, 138);
    border-radius: 5px;
    transition: background-color 125ms;
  }

  #submit-btn:hover {
    cursor: pointer;
    background-color: #0d7583;
  }

  /* Feedback star text */
  .feedback-box {
    display: flex;
    align-items: end;
    column-gap: 5px;
  }

  .star:hover {
    cursor: pointer;
  }

  .active-star {
    color: gold;
  }

  .inactive-star {
    color: #ccc;
  }

  .feedback-text {
    resize: none;
    height: 64px;
    border-color: rgb(221, 221, 221);
    padding: 5px;
    border-radius: 5px;
    font-family: Arial, Helvetica, sans-serif;
    font-weight: 300;
  }

  .feedback-text:hover {
    outline: none;
  }

  .feedback-text:focus {
    outline: none;
  }

  .feedback-btn {
    height: 39px;
    width: auto;
    background-color: #47b6f9;
    color: white;
    border: 1px solid rgb(221, 221, 221);
    border-radius: 5px;
  }

  .feedback-btn:hover {
    cursor: pointer;
    background-color: #64c0f8;
  }

  .feedback-thank-text {
    color: rgb(172, 172, 172);
    font-size: 13px;
    margin-top: 0;
    font-family: Arial, Helvetica, sans-serif;
  }
</style>

<div id="chat-container">
  <div id="header-view">
    <div id="left-header">
      <div class="chat-icon-container">
        <img src="https://kommun.falkenberg.se/images/ai_falken.png" alt="" class="chat-icon" />
      </div>
      <h5 class="default-text" id="bot-name">Fråga Falkis</h5>
    </div>
    <span uk-icon="icon: chevron-down" id="header-icon"></span>
  </div>
  <div id="chat-wrapper">
    <p class="default-text" id="disclaimer">
      <small>AI kan begå misstag. Kontrollera viktig information. <a href="https://kommun.falkenberg.se/om-kommunen/om-webbplatsen/om-falkis">Läs mer</a></small>
    </p>
    <div id="message-container"></div>
  </div>
  <form action="" id="answer-view">
    <span uk-icon="icon: file-edit; ratio: 2" id="clear-chat-button"></span>
    <input type="text" name="user-answer" id="user-answer" placeholder="Skriv din fråga här." autocomplete="off"
      maxlength="200" />
    <input type="button" name="submit-btn" id="submit-btn" value="Skicka" />
  </form>
</div>
<script src="https://cdn.jsdelivr.net/npm/showdown/dist/showdown.min.js"></script>
<script>
  // **Initialization Code**
// ----------HN-----------

let isUp = loadIsUp();
let allowClickHeader = true;

const messageContainer = document.getElementById("message-container");
let reset_message_on = false;

// Append the start message
createBotMessage("Hejsan! Vad kan jag hjälpa till med?");

loadChatFromSession();

// **Event Listeners**
// -------------------

// Clear Chat Button
document
  .getElementById("clear-chat-button")
  .addEventListener("click", function () {
    clearChat();
  });

// Enter Text Send
document
  .getElementById("user-answer")
  .addEventListener("keypress", function (event) {
    if (event.key === "Enter") {
      event.preventDefault();
      sendAndPrintAnswer();
    }
  });

// Button Text Send
document.getElementById("submit-btn").addEventListener("click", function () {
  sendAndPrintAnswer();
});

// Header View Click (Open/Close Bot)
document.getElementById("header-view").addEventListener("click", function () {
  openCloseBot(true);
});

// **Main Functions**
// ------------------

// Function to send and print answer
async function sendAndPrintAnswer() {
  const inputText = document.getElementById("user-answer");
  const submitBtn = document.getElementById("submit-btn");
  let inputValue = inputText.value;

  if (inputValue !== "") {
    activateUserInput(false);
    turnActiveAll(false);
    try {
      const piiDetected = await checkPII(inputValue);
      console.log(piiDetected);

      if (piiDetected) {
        showConfirmationScreen(() => {
          sendQuestion(inputText, submitBtn);
        });
        console.log("Nått speciellt hittat");
      } else {
        console.log("Inget speciellt");
        sendQuestion(inputText, submitBtn);
      }
    } catch (error) {
      console.log("Ett fel uppstod", error);
      loadUserText(inputValue);

      clearUserAndSurroundings();

      createBotMessage(
        "Servern verkar ha problem just nu. Försök gärna igen senare."
      );

      activateUserInput(true);
      turnActiveAll(true);
    }
  }
}

// Function to send question
function sendQuestion(inputText) {
  let inputValue = inputText.value;
  loadUserText(inputValue);

  clearUserAndSurroundings();
  try {
    getBotAnswer(inputValue, () => {
      activateUserInput(true);
      turnActiveAll(true);
    });
  } catch (error) {
    console.log("Misslyckades att hämta svar!", error);
    activateUserInput(true);
    turnActiveAll(true);
  };
}

// Function to get bot's answer
function getBotAnswer(user_question, callback) {
  const botMessageElement = createBotMessage("ㅤ");
  const messageContainer = document.getElementById("message-container");
  let chat_id = messageContainer.dataset.chat_id || null;

  const user_history = loadConvToOpenAIJson();

  // Loader animation
  let loadingText = "";
  let loadingIndex = 0;
  const loadingInterval = setInterval(() => {
    loadingText = ".".repeat((loadingIndex % 3) + 1);
    updateBotMessageElement(botMessageElement, loadingText);
    loadingIndex++;
  }, 300);

  console.log(user_question, user_history, chat_id);
  fetch("https://falkisapi.utvecklingfalkenberg.se/generate", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      user_input: user_question,
      user_history: user_history,
      chat_id: chat_id,
    }),
  })
    .then((response) => {
      if (response.status === 429) {
        errormessage =
          "Jag har svarat på många frågor och behöver nu vila ett tag, fråga igen senare.";
        updateBotMessageElement(botMessageElement, errormessage);
        pushMessageToSession(user_question, errormessage);
        callback();
        return;
      } else if (response.status === 500) {
        const errormessage =
          "Servern verkar ha problem just nu. Försök gärna igen senare.";
        updateBotMessageElement(botMessageElement, errormessage);
        pushMessageToSession(user_question, errormessage);
        callback();
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let result = "";
      let receivedText = "";
      let sources = null;
      let initialJsonDone = false;
      function read() {
        reader.read().then(({ done, value }) => {
          if (done) {
            pushMessageToSession(user_question, result, chat_id);
            addRatingSystem(botMessageElement, user_question, result);

            callback();
            return;
          }

          const chunk = decoder.decode(value, { stream: true });
          receivedText += chunk;
          if (initialJsonDone != true) {
            console.log(
              "Nu vid första iterationen ska splittas: ",
              receivedText
            );
            const separator = "\n<END_OF_JSON>\n";
            const separatorIndex = receivedText.indexOf(separator);
            if (separatorIndex !== -1) {
              const jsonStr = receivedText.slice(0, separatorIndex);
              console.log("Sträng ", jsonStr);
              try {
                const json = JSON.parse(jsonStr);

                sources = json.sources;

                if (chat_id === null && json.chat_id) {
                  chat_id = json.chat_id;
                  messageContainer.dataset.chat_id = chat_id;
                }

                initialJsonDone = true;
              } catch (e) {
                console.error("Kunde inte parsa JSON-data:", e);
              }
              console.log("Json Parsed done:", initialJsonDone);
              receivedText = receivedText.slice(
                separatorIndex + separator.length
              );
              console.log("Resterande text: ", receivedText);
              result += receivedText;
              receivedText = "";
              updateBotMessageElement(botMessageElement, result);
            }
          } else {
            result += chunk;
            updateBotMessageElement(botMessageElement, result);
          }

          scrollToBottom();
          read();
        });
      }

      clearInterval(loadingInterval);
      read();
    })
    .catch((error) => {
      console.error("Error:", error);
      clearInterval(loadingInterval);
      errormessage = "Något gick fel! Jag kunde inte hitta något svar på det.";
      updateBotMessageElement(botMessageElement, errormessage);
      pushMessageToSession(user_question, errormessage);
      callback();
    });
}
async function checkPII(userInput) {
  const response = await fetch("https://falkisapi.utvecklingfalkenberg.se/check_pii", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_input: userInput }),
  });
  const data = await response.json();
  return data.pii_detected;
}

// Function to show confirmation screen
function showConfirmationScreen(onConfirm) {
  let screen = document.getElementById("confirmation-screen");
  if (!screen) {
    screen = document.createElement("div");
    screen.id = "confirmation-screen";
    screen.style.display = "flex";
    const confirm_header = document.createElement("div");
    confirm_header.id = "confirm-header";
    confirm_header.textContent = "Varning!";
    confirm_header.className = "default-text";
    const screen_content = document.createElement("div");
    const confirmation_text = document.createElement("p");
    confirmation_text.textContent =
      "Du verkar eventuellt ha skrivit in personuppgifter. Vill du verkligen skicka?";
    confirmation_text.className = "default-text";
    const button_div = document.createElement("div");
    button_div.id = "button-div";
    const button_yes = document.createElement("button");
    button_yes.id = "confirm-yes";
    button_yes.className = "default-text";
    button_yes.textContent = "Ja!";
    const button_no = document.createElement("button");
    button_no.id = "confirm-no";
    button_no.textContent = "Nej!";
    button_div.appendChild(button_yes);
    button_div.appendChild(button_no);
    screen_content.appendChild(confirmation_text);
    screen_content.appendChild(button_div);
    screen.appendChild(confirm_header);
    screen.appendChild(screen_content);
    const chat_container = document.getElementById("chat-container");
    chat_container.appendChild(screen);

    //Event listeners on buttons
    button_yes.onclick = function () {
      screen.style.display = "none";
      turnActiveAll(true);
      onConfirm();
    };

    button_no.onclick = function () {
      screen.style.display = "none";
      turnActiveAll(true);
      activateUserInput(true);
    };
  } else {
    screen.style.display = "flex";
    turnActiveAll(false);
  }
}

// **User Interaction Functions**
// ------------------------------

// Function to load user text
function loadUserText(text) {
  const message_container = document.getElementById("message-container");

  const user_text_box = document.createElement("div");
  user_text_box.setAttribute("class", "user-container");
  const new_text = document.createElement("b");
  new_text.setAttribute("class", "user-text default-text");
  new_text.textContent = text;

  user_text_box.appendChild(new_text);
  message_container.appendChild(user_text_box);
  scrollToBottom();
}

// Function to create bot message element
function createBotMessage(initialText) {
  const boxContainer = document.createElement("div");
  boxContainer.className = "bot-container";
  // Add icon
  const iconDiv = document.createElement("div");
  iconDiv.className = "flex-icon";
  const chatIconContainer = document.createElement("div");
  chatIconContainer.className = "chat-icon-container";
  const chatIcon = document.createElement("img");
  chatIcon.src = "https://kommun.falkenberg.se/images/ai_falken.png";
  chatIcon.alt = "";
  chatIcon.className = "chat-icon";
  chatIconContainer.appendChild(chatIcon);
  iconDiv.appendChild(chatIconContainer);
  boxContainer.appendChild(iconDiv);

  // Add message
  const messageDiv = document.createElement("div");
  messageDiv.className = "bot-message";
  const botName = document.createElement("h5");
  botName.className = "default-text fine-bot-name";
  botName.textContent = "Falkis";
  const botText = document.createElement("b");
  botText.className = "default-text bot-text";

  messageDiv.appendChild(botName);
  messageDiv.appendChild(botText);
  boxContainer.appendChild(messageDiv);

  updateBotMessageElement(boxContainer, initialText);

  const messageContainer = document.getElementById("message-container");
  messageContainer.appendChild(boxContainer);
  scrollToBottom();
  return boxContainer;
}

// Function to update bot message element
function updateBotMessageElement(botMessageElement, newText) {
  const botText = botMessageElement.querySelector(".bot-text");
  botText.innerHTML = makeTextMarkdown(newText);

  const links = botText.querySelectorAll("a");
  links.forEach((link) => {
    link.setAttribute("target", "_blank");
    link.setAttribute("rel", "noopener noreferrer");
  });

  scrollToBottom();
}

// Function to scroll to bottom of chat
function scrollToBottom() {
  const messageContainer = document.getElementById("message-container");
  messageContainer.scrollTop = messageContainer.scrollHeight;
}

// **Message Copy Icon**
// ---------------------
function addCopyIcon(botContainer, result) {
  //parentElement = botContainer.querySelector(".bot-message")
  const copyButton = document.createElement("span");
  copyButton.setAttribute("uk-icon", "icon: copy");
  copyButton.className = "copy-button";

  const copyMessage = document.createElement("p");
  copyMessage.className = "copy-message default-text";
  copyMessage.textContent = "Kopierat!";

  copyButton.addEventListener("click", function () {
    copyText(result);
    copyMessageShow(copyButton);
  });
  copyButton.appendChild(copyMessage);
  botContainer.appendChild(copyButton);
}

// Copy text
function copyText(text) {
  navigator.clipboard.writeText(text);
}

// Copy message appearance
function copyMessageShow(copyButton) {
  const message = copyButton.firstChild;
  message.style.visibility = "visible";
  message.style.opacity = "1";
  message.style.visibility = "visible";
  message.style.opacity = "1";
  setTimeout(() => {
    message.style.visibility = "hidden";
    message.style.opacity = "0";
  }, 1500);
}

// **Feedback and Rating System Functions**
// ----------------------------------------

// Function to add rating system
function addRatingSystem(
  botMessageElement,
  question,
  answer,
  startFeedbackValue,
  startStars
) {
  const botMessageContainer = botMessageElement.querySelector(".bot-message");
  const ratingContainer = document.createElement("div");
  ratingContainer.className = "rating-container";
  ratingContainer.dataset.starValue = "0";

  /// Add copy button
  addCopyIcon(ratingContainer, answer);

  for (let i = 1; i <= 5; i++) {
    const star = document.createElement("span");
    star.className = "star inactive-star";
    star.innerHTML = "&#9734;";
    star.dataset.value = i;
    ratingContainer.appendChild(star);
  }

  if (startFeedbackValue) {
    ratingContainer.dataset.feedbackValue = startFeedbackValue;
  } else {
    ratingContainer.dataset.feedbackValue = "0";
  }
  if (startStars) {
    fillStars(ratingContainer, startStars, true);
    createFeedbackThank(ratingContainer);
  }

  ratingContainer.addEventListener("mouseover", (event) => {
    if (event.target.classList.contains("star")) {
      fillStars(ratingContainer, event.target.dataset.value);
    }
  });
  ratingContainer.addEventListener("mouseout", () => {
    fillStars(ratingContainer, ratingContainer.dataset.starValue);
  });
  ratingContainer.addEventListener("click", (event) => {
    if (event.target.classList.contains("star")) {
      ratingContainer.dataset.starValue = toggleFeedbackBox(
        ratingContainer,
        question,
        answer,
        event.target.dataset.value,
        ratingContainer.dataset.starValue
      );
    }
  });

  botMessageContainer.appendChild(ratingContainer);

  //Create message to tell user to reset for more relevant answers
  const chatHistory = JSON.parse(sessionStorage.getItem("chatHistory")) || [];
  if (chatHistory.length >= 7 && !reset_message_on) {
    reset_message = document.createElement("small");
    reset_message.id = "reset-message";
    reset_message.className = "default-text";
    reset_message.textContent =
      "Vi rekommenderar att skapa en ny chatt för att få mer relevanta svar!";

    chatContainer = document.getElementById("chat-container");
    input_form = document.getElementById("answer-view");
    chatContainer.insertBefore(reset_message, input_form);
    reset_message_on = true;
  }

  scrollToBottom();
}

// Function to fill stars
function fillStars(container, value, forceStar) {
  const stars = container.querySelectorAll(".star");
  if (container.dataset.feedbackValue !== "1" || forceStar == true) {
    stars.forEach((star) => {
      if (star.dataset.value <= value) {
        star.innerHTML = "&#9733;";
        star.classList.add("active-star");
        star.classList.remove("inactive-star");
      } else {
        star.innerHTML = "&#9734;";
        star.classList.add("inactive-star");
        star.classList.remove("active-star");
      }
    });
    container.dataset.rating = value;
  } else {
    stars.forEach((star) => {
      star.style.cursor = "default";
    });
  }
}

// Function to toggle feedback box
function toggleFeedbackBox(container, question, answer, newRating, oldRating) {
  const feedbackSent = Number(container.dataset.feedbackValue);

  if (feedbackSent !== 1) {
    let feedbackBox = container.querySelector(".feedback-box");
    if (!feedbackBox) {
      feedbackBox = document.createElement("div");
      feedbackBox.className = "feedback-box";

      const textarea = document.createElement("textarea");
      textarea.className = "feedback-text";
      textarea.spellcheck = false;
      textarea.placeholder = "Lämna din feedback om svaret här...";
      textarea.maxLength = "200";
      feedbackBox.appendChild(textarea);

      const submitButton = document.createElement("button");
      submitButton.textContent = "Skicka";
      submitButton.className = "feedback-btn";
      feedbackBox.appendChild(submitButton);
      container.appendChild(feedbackBox);
    }

    const submitButton = container.querySelector(".feedback-btn");
    const textarea = container.querySelector(".feedback-text");
    submitButton.onclick = () => {
      submitFeedback(newRating, textarea.value);
      container.dataset.feedbackValue = "1";
      feedbackBox.remove();
      const message_container = document.getElementById("message-container");
      const chat_id = message_container.dataset.chat_id;
      pushMessageToSession(
        question,
        answer,
        chat_id,
        container.dataset.feedbackValue,
        newRating
      );
      createFeedbackThank(container);
      if (textarea.value === "clear") {
        clearChat();
      }
    };

    if (newRating !== oldRating) {
      feedbackBox.style.display = "flex";
      scrollToBottom();
      return newRating;
    } else {
      feedbackBox.style.display = "none";
      return "0";
    }
  }
}

// Function to create feedback thank you message
function createFeedbackThank(container) {
  const feedbackThank = document.createElement("p");
  feedbackThank.className = "default-text feedback-thank-text";
  feedbackThank.textContent = "Tack för din feedback!";
  container.appendChild(feedbackThank);
}

// Function to submit feedback to backend
async function submitFeedback(user_rating, user_feedback) {
  let message_container = document.getElementById("message-container");
  let chat_id = message_container.dataset.chat_id;
  let feedbackData = {};

  feedbackData.chat_id = chat_id;
  feedbackData.user_rating = user_rating;
  if (user_feedback) feedbackData.user_feedback = user_feedback;

  console.log(feedbackData);
  fetch("https://falkisapi.utvecklingfalkenberg.se/feedback", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(feedbackData),
  })
    .then((response) => {
      if (!response.ok) {
        return response.json().then((errorData) => {
          throw new Error(errorData.error);
        });
      }
      return response.json();
    })
    .catch((error) => {
      console.error("Error:", error.message);
    });
}

// **Session Storage Functions**
// -----------------------------

// Function to push message to session storage
function pushMessageToSession(
  question,
  answer,
  chat_id,
  feedback_state,
  nr_stars
) {
  const chatHistory = JSON.parse(sessionStorage.getItem("chatHistory")) || [];

  const existingEntryIndex = chatHistory.findIndex(
    (entry) => entry.question === question && entry.answer === answer
  );

  if (existingEntryIndex !== -1) {
    // Update Existing
    if (feedback_state !== null)
      chatHistory[existingEntryIndex].feedback_state = feedback_state;
    if (nr_stars !== null) chatHistory[existingEntryIndex].nr_stars = nr_stars;
  } else {
    // Add new
    const newEntry = { question, answer };

    if (feedback_state !== null) newEntry.feedback_state = feedback_state;
    if (nr_stars !== null) newEntry.nr_stars = nr_stars;

    chatHistory.push(newEntry);
  }

  sessionStorage.setItem("chatHistory", JSON.stringify(chatHistory));
  sessionStorage.setItem("currentChatId", chat_id);
}

// Function to load chat from session storage
function loadChatFromSession() {
  const chatHistory = JSON.parse(sessionStorage.getItem("chatHistory")) || [];
  const currentChatId = sessionStorage.getItem("currentChatId");
  const messageContainer = document.getElementById("message-container");
  if (currentChatId !== null) {
    messageContainer.dataset.chat_id = currentChatId;
  }
  chatHistory.forEach((item, index) => {
    loadUserText(item.question);
    const botMessageElement = createBotMessage(item.answer);
    if (index === chatHistory.length - 1) {
      addRatingSystem(
        botMessageElement,
        item.question,
        item.answer,
        item.feedback_state,
        item.nr_stars
      );
    }
  });
  openCloseBot(false);
}

// Function to load conversation to OpenAI JSON format
function loadConvToOpenAIJson() {
  const chatHistory = JSON.parse(sessionStorage.getItem("chatHistory")) || [];
  let user_history = [];
  chatHistory.forEach((item) => {
    user_history.push({ role: "user", content: item.question });
    user_history.push({ role: "assistant", content: item.answer });
  });
  console.log(user_history);
  return user_history;
}

// **Utility Functions**
// ---------------------

// Function to clear chat
function clearChat() {
  sessionStorage.removeItem("chatHistory");
  sessionStorage.removeItem("currentChatId");
  const chat_container = document.getElementById("message-container");
  chat_container.innerHTML = "";
  delete chat_container.dataset.chat_id;

  createBotMessage("Hejsan! Vad kan jag hjälpa till med?");
  activateUserInput(true);

  const reset_message = document.getElementById("reset-message");
  reset_message?.remove();
}

// Function to toggle on/off interactable of elements
function turnActiveAll(state) {
  const chat_container = document.getElementById("chat-container");
  const childrens = Array.from(chat_container.children);
  childrens.forEach((item) => {
    if (!state && item.id !== "confirmation-screen") {
      item.classList.add("inactive-el");
    } else {
      item.classList.remove("inactive-el");
    }
  });
}

function activateUserInput(state) {
  const inputText = document.getElementById("user-answer");
  const submitBtn = document.getElementById("submit-btn");
  if (state) {
    inputText.disabled = false;
    submitBtn.disabled = false;
    inputText.focus();
  } else {
    inputText.disabled = true;
    submitBtn.disabled = true;
  }
}

// Function to clear input field by ID
function clearUserAndSurroundings() {
  document.getElementById("user-answer").value = "";
  document
    .querySelectorAll(".rating-container")
    .forEach((element) => element.remove());

  document.getElementById("reset_message")?.remove();
}

//Turn to markdown format
function makeTextMarkdown(text) {
  const converter = new showdown.Converter();
  const markedText = converter.makeHtml(text);
  return markedText;
}

//Turn on/off header icon
function showHeaderIcon(show = true) {
  const headerIcon = document.getElementById("header-icon");
  if (show) {
    headerIcon.style.visibility = "visible";
    headerIcon.style.opacity = "1";
    headerIcon.style.flex = "0 0 20px";
  } else {
    headerIcon.style.opacity = "0";
    headerIcon.style.flex = "0 0 0px";
    headerIcon.style.visibility = "hidden";
  }
}

// **Load and Save Functions for 'isUp' Variable**
// -----------------------------------------------

// Function to load 'isUp' variable from session storage
function loadIsUp() {
  const isUpString = sessionStorage.getItem("isUp");
  if (isUpString) {
    return isUpString !== "true";
  } else {
    return true;
  }
}

// Function to save 'isUp' variable to session storage
function saveIsUp(state) {
  sessionStorage.setItem("isUp", state);
}

// Function to open/close bot
function openCloseBot(doAnimation) {
  const chatContainer = document.getElementById("chat-container");
  let delayTime = 500;

  if (!doAnimation) {
    chatContainer.style.transition = "none";
    delayTime = 0;
  } else {
    chatContainer.style.transition = "height 0.5s ease, width 0.5s ease";
  }
  let windowWidth = document.documentElement.clientWidth;
  if (allowClickHeader) {
    allowClickHeader = false;
    if (windowWidth < 450) {
      if (!isUp) {
        chatContainer.style.width = "100dvw";
        setTimeout(() => {
          chatContainer.style.minWidth = "340px";
          chatContainer.style.height = "100dvh";
          showHeaderIcon(true);
        }, delayTime);
        isUp = true;
      } else {
        chatContainer.style.height = "56px";
        showHeaderIcon(false);
        setTimeout(() => {
          chatContainer.style.width = "200px";
          chatContainer.style.minWidth = "0";
        }, delayTime);
        isUp = false;
      }
    } else if (!isUp) {
      chatContainer.style.width = "450px";
      setTimeout(() => {
        chatContainer.style.height = "470px";
        showHeaderIcon(true);
      }, delayTime);
      isUp = true;
    } else {
      chatContainer.style.height = "56px";
      showHeaderIcon(false);
      setTimeout(() => {
        chatContainer.style.minWidth = "0";
        chatContainer.style.width = "200px";
      }, delayTime);
      isUp = false;
    }

    setTimeout(() => {
      allowClickHeader = true;
    }, delayTime + 500);
  }
  saveIsUp(isUp);
}
</script>
</div>
