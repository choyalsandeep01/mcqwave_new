document.addEventListener('DOMContentLoaded', function () {
    const subjectSelect = document.getElementById('id_subject');
    const unitSelect = document.getElementById('id_unit');
    const chapterSelect = document.getElementById('id_chapter');
    const topicSelect = document.getElementById('id_topic');

    subjectSelect.addEventListener('change', function () {
        const subjectId = this.value;
        fetch(`/my_app//?subject_id=${subjectId}`)
            .then(response => response.json())
            .then(data => {
                unitSelect.innerHTML = '<option value="">Select Unit</option>';
                data.forEach(unit => {
                    unitSelect.innerHTML += `<option value="${unit.id}">${unit.name}</option>`;
                });
                chapterSelect.innerHTML = '<option value="">Select Chapter</option>';
                topicSelect.innerHTML = '<option value="">Select Topic</option>';
            });
    });

    unitSelect.addEventListener('change', function () {
        const unitId = this.value;
        fetch(`/my_app/get-chapters/?unit_id=${unitId}`)
            .then(response => response.json())
            .then(data => {
                chapterSelect.innerHTML = '<option value="">Select Chapter</option>';
                data.forEach(chapter => {
                    chapterSelect.innerHTML += `<option value="${chapter.id}">${chapter.name}</option>`;
                });
                topicSelect.innerHTML = '<option value="">Select Topic</option>';
            });
    });

    chapterSelect.addEventListener('change', function () {
        const chapterId = this.value;
        fetch(`/my_app/get-topics/?chapter_id=${chapterId}`)
            .then(response => response.json())
            .then(data => {
                topicSelect.innerHTML = '<option value="">Select Topic</option>';
                data.forEach(topic => {
                    topicSelect.innerHTML += `<option value="${topic.id}">${topic.name}</option>`;
                });
            });
    });
});
