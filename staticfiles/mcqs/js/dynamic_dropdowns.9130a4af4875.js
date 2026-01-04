document.addEventListener('DOMContentLoaded', function () {
    const subjectDropdown = document.getElementById('id_subject');
    const unitDropdown = document.getElementById('id_unit');
    const chapterDropdown = document.getElementById('id_chapter');
    const topicDropdown = document.getElementById('id_topic');

    subjectDropdown.addEventListener('change', function () {
        const subjectId = this.value;
        fetch(`/mcqs/get-units/?subject_id=${subjectId}`)
            .then(response => response.json())
            .then(data => {
                if (data.units) {
                    unitDropdown.innerHTML = '<option value="">Select a unit</option>';
                    data.units.forEach(unit => {
                        unitDropdown.innerHTML += `<option value="${unit.id}">${unit.name}</option>`;
                    });
                } else {
                    console.error('No units data found:', data);
                }
            })
            .catch(error => console.error('Error:', error));
    });

    unitDropdown.addEventListener('change', function () {
        const unitId = this.value;
        fetch(`/mcqs/get-chapters/?unit_id=${unitId}`)
            .then(response => response.json())
            .then(data => {
                if (data.chapters) {
                    chapterDropdown.innerHTML = '<option value="">Select a chapter</option>';
                    data.chapters.forEach(chapter => {
                        chapterDropdown.innerHTML += `<option value="${chapter.id}">${chapter.name}</option>`;
                    });
                } else {
                    console.error('No chapters data found:', data);
                }
            })
            .catch(error => console.error('Error:', error));
    });

    chapterDropdown.addEventListener('change', function () {
        const chapterId = this.value;
        fetch(`/mcqs/get-topics/?chapter_id=${chapterId}`)
            .then(response => response.json())
            .then(data => {
                if (data.topics) {
                    topicDropdown.innerHTML = '<option value="">Select a topic</option>';
                    data.topics.forEach(topic => {
                        topicDropdown.innerHTML += `<option value="${topic.id}">${topic.name}</option>`;
                    });
                } else {
                    console.error('No topics data found:', data);
                }
            })
            .catch(error => console.error('Error:', error));
    });
});
