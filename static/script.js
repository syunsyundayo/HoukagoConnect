for (const element of document.querySelectorAll('time[datetime]')) {
  const date = new Date(element.dateTime);
  if (!Number.isNaN(date.getTime())) {
    element.textContent = new Intl.DateTimeFormat('ja-JP', {
      timeZone: 'Asia/Tokyo', dateStyle: 'medium', timeStyle: 'short'
    }).format(date);
  }
}

const upload = document.querySelector('#upload');
upload?.addEventListener('change', () => {
  const file = upload.files[0];
  const status = document.querySelector('#file-status');
  const oversized = file && file.size > 5 * 1024 * 1024;
  upload.setCustomValidity(oversized ? '画像は5 MB以下にしてください。' : '');
  status.textContent = oversized ? upload.validationMessage : (file?.name ?? '');
});
