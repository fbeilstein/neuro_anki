document.addEventListener('DOMContentLoaded', function () {
    const input = document.getElementById('user-input');
    const form = document.getElementById('ans-form');
    const answerBox = document.getElementById('answer-box');
    const hiddenGrade = document.getElementById('hidden-grade');
    const audio = document.getElementById('audio-player');
    const config = document.getElementById('logic-config');

    // 1. Data Normalization
    // Strips: leading/trailing spaces, repeated spaces, punctuation,
    //         arithmetic signs (+,-,=,<,>), and lowercases everything.
    function normalize(text) {
        if (!text) return "";
        return text.toString()
            .trim()
            .toLowerCase()
            .replace(/[\s]+/g, " ")                          // collapse multiple spaces
            .replace(/[.,\/#!$%\^&\*;:{}=\-_`~()\[\]<>+'"«»–—…?!¿¡]/g, "")  // strip punctuation & arithmetic
            .replace(/\s+/g, " ")                            // re-collapse after stripping
            .trim();
    }

    // 2. Event Listener
    if (input) {
        input.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') {
                e.preventDefault();

                // If shown, submit
                if (input.readOnly) {
                    form.submit();
                    return;
                }

                // 3. READ CONFIGURATION FROM HTML DATA ATTRIBUTES
                // We parse the JSON string back into a real Array
                const validAnswers = JSON.parse(config.dataset.valid);
                const primaryAnswer = config.dataset.primary;

                // 4. Validation Logic
                const userVal = normalize(input.value);
                const validSet = validAnswers.map(normalize);
                const isCorrect = validSet.includes(userVal);

                // 5. UI Updates
                input.readOnly = true;
                answerBox.style.display = 'block';

                if (isCorrect) {
                    input.style.backgroundColor = '#2d4a33';
                    input.style.color = '#4cd964';
                    hiddenGrade.value = "1";
                } else {
                    input.style.backgroundColor = '#4a2d2d';
                    input.style.color = '#ff6b6b';
                    input.value += " → " + primaryAnswer;
                    hiddenGrade.value = "0";
                }

                if (audio) audio.play();
            }
        });
    }
});
