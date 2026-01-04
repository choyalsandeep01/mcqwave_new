function calculateTimeSpent(uid) {
        
    if (!currentQuestionStartTime) return; // If no start time, return

    const endTime = Date.now();
    const timeSpent = (endTime - currentQuestionStartTime) / 1000; // Time in seconds

    // If this question already has some time tracked, add to it
    if (questionTimes[uid]) {
        questionTimes[uid] += timeSpent;
        console.log(questionTimes);
    } else {
        questionTimes[uid] = timeSpent;
    }
    
    var test_id = '{{ test_id }}';  // Pass the test_id to the function
    
    const csrftoken = getCookie('csrftoken');
        $.ajax({
            url: '/mcqs/save-answer/',
            type: 'POST',
            data: {
                'test_id': test_id,
                'mcq_uid': uid,
                'time_spent': questionTimes[uid],
            },
            headers: {
                'X-CSRFToken': csrftoken  // Include the CSRF token in the header
            },
            success: function (response) {
                console.log('Answer and time saved successfully');
            },
            error: function (xhr, status, error) {
                console.error('Error saving answer:', error);
                console.log('Status:', status);
                console.log('Response:', xhr.responseText);
            }
        });
    console.log(typeof(questionTimes[uid]));
    console.log(`Time spent on question ${uid}: ${questionTimes[uid]} seconds`);
}





function submitQuiz() {
    
    
    const mcq = mcqs[current_que_index];
    if (!isReviewMode) {
        console.log('CURRENTUID:', currentQuestionUID);
        const mcquid = mcq.uid;
        if (currentQuestionUID) {
            calculateTimeSpent(currentQuestionUID);
        }
        
        // Set the current question UID and start time
       
}
const csrftoken = getCookie('csrftoken');
const testId = '{{ test_id }}';
$.ajax({
    url: '/mcqs/submitted_active/',
    type: 'POST',
    data: {
        'test_id': testId,
    },
    headers: {
        'X-CSRFToken': csrftoken // Include the CSRF token in the header
    },
    success: function(response) {
        console.log('Test submitted successfully');
        
        // Now call the submit_quiz function after confirming test session submission
        submitQuizData();
    },
    error: function(xhr, status, error) {
        console.error('Error submitting test:', error);
        console.log('Status:', status);
        console.log('Response:', xhr.responseText);
    }
});
}





function selectOption(selectedLi, index) {
    const optionsList = document.querySelectorAll('.options li');
    const selectedInput = selectedLi.querySelector('input');
    
    const selectedValue = selectedInput.value;
    const selectedText = selectedLi.textContent.trim();
    // Check if the selected option is already checked
    const isAlreadySelected = selectedLi.classList.contains('selected');

    // Unselect all options
    optionsList.forEach(li => {
        li.classList.remove('selected'); // Remove 'selected' class from all options
        li.querySelector('input').checked = false; // Uncheck all options
    });
    
    if (!isAlreadySelected) {
        // Select the clicked option
        selectedLi.classList.add('selected');
        selectedInput.checked = true;
        selectedAnswers[index] = selectedValue;
        selectedAnswerTexts[index] = selectedText;
        var selected_option = selectedValue;
    } else {
        // Unselect the clicked option
        selectedAnswers[index] = null;
        selectedAnswerTexts[index] = null;
        var selected_option = '';
    }
    
    var mcq_uid = mcqs[index].uid
    var test_id = '{{ test_id }}';  // Pass the test_id to the function
      // Function to get the remaining time
    console.log(selected_option);
    console.log(mcq_uid);
    console.log(test_id);
    
    // Update the navigation button color based on the new selection state
    updateNavButtonColor(index, selectedAnswers[index] ? 'green' : reviewQuestions[index] ? 'yellow' : 'white');
    
    // Update the review status circle
    updateReviewStatusCircle();
    
    console.log("CHLA");
    const csrftoken = getCookie('csrftoken');
        $.ajax({
            url: '/mcqs/save-answer/',
            type: 'POST',
            data: {
                'test_id': test_id,
                'mcq_uid': mcq_uid,
                'selected_option': selected_option,
            },
            headers: {
                'X-CSRFToken': csrftoken  // Include the CSRF token in the header
            },
            success: function (response) {
                console.log('Answer and time saved successfully');
            },
            error: function (xhr, status, error) {
                console.error('Error saving answer:', error);
                console.log('Status:', status);
                console.log('Response:', xhr.responseText);
            }
        });
        console.log("DONE");
}