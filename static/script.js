document.addEventListener('DOMContentLoaded', () => {
    // Populate location dropdown from dataset
    fetch('/static/data/dataset.json')
        .then(res => res.json())
        .then(data => {
            const citySelect = document.getElementById('currentLocation');
            const cities = Array.from(new Set(data.map(item => item.name).filter(Boolean)))
                .sort((a, b) => a.localeCompare(b));
            cities.forEach(city => {
                const option = document.createElement('option');
                option.value = city;
                option.textContent = city;
                citySelect.appendChild(option);
            });
        })
        .catch(err => console.error('Error loading dataset:', err));

    // Step form logic
    const form = document.getElementById('vacationForm');
    const questions = form.querySelectorAll('.question');
    const nextButtons = form.querySelectorAll('.next');
    const prevButtons = form.querySelectorAll('.prev');
    const progress = document.getElementById('progress');
    const steps = document.querySelectorAll('.step');
    const submitButton = form.querySelector('.submit');
    let currentStep = 0;

    function updateStep() {
        questions.forEach((q, i) => {
            q.classList.toggle('active', i === currentStep);
        });
        steps.forEach((s, i) => {
            s.classList.toggle('active', i <= currentStep);
        });
        progress.style.width = `${(currentStep / (steps.length - 1)) * 100}%`;
    }

    nextButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            if (currentStep < questions.length - 1) {
                currentStep++;
                updateStep();
            }
        });
    });

    prevButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            if (currentStep > 0) {
                currentStep--;
                updateStep();
            }
        });
    });

    


let resultDiv = null;

    // Submit form handler
submitButton.addEventListener('click', async (e) => {
    e.preventDefault();

    const imageInput = document.getElementById("imageUpload");
    if (!imageInput || imageInput.files.length === 0) {
        alert("Please upload an image to continue.");
        return;
    }

    const formData = new FormData(form);

    // Create result div if it doesn't exist
    if (!resultDiv) {
        resultDiv = document.createElement('div');
        resultDiv.id = 'result';
        resultDiv.style.marginTop = '40px';
        resultDiv.style.padding = '20px';
        resultDiv.style.border = '2px solid #ccc';
        resultDiv.style.borderRadius = '12px';
        resultDiv.style.backgroundColor = '#f9f9f9';
        form.parentNode.appendChild(resultDiv);
    }

    resultDiv.innerHTML = "<p>⏳ Finding your perfect vacation...</p>";

    try {
        const response = await fetch('/recommend', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (data.success) {
            resultDiv.innerHTML = `
                <h3>🌟 We Recommend: <span style="color: #007BFF">${data.recommendation.destination}</span></h3>
                <p>${data.recommendation.why_perfect}</p>
                <div class="details">
                    <p><strong>📍 Location:</strong> ${data.recommendation.location}</p>
                    <p><strong>📅 Best Season:</strong> ${data.recommendation.best_season}</p>
                    <p><strong>💡 Itinerary Tip:</strong> ${data.recommendation.local_tip || data.recommendation.itinerary_tip}</p>
                </div>
            `;
        } else {
            resultDiv.innerHTML = `
                <p class="error">❌ Error: ${data.error}</p>
                ${data.tip ? `<p><em>Tip: ${data.tip}</em></p>` : ""}
            `;
        }
    } catch (error) {
        resultDiv.innerHTML = `<p class="error">❌ Network error: ${error.message}</p>`;
    }
});

    updateStep();
});

document.addEventListener('DOMContentLoaded', () => {
    const contactForm = document.getElementById('contactForm');
    const statusEl = document.getElementById('formStatus');

    if (contactForm) {
        contactForm.addEventListener('submit', async (e) => {
            e.preventDefault();

            statusEl.textContent = "Sending...";
            statusEl.className = "form-status";

            try {
                const response = await fetch('/submit-contact', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Accept': 'application/json'
                    },
                    body: JSON.stringify({
                        name: document.getElementById('name').value,
                        email: document.getElementById('email').value,
                        message: document.getElementById('message').value
                    })
                });

                let result = {};
                const contentType = response.headers.get("content-type") || "";
                if (contentType.includes("application/json")) {
                    result = await response.json();
                } else {
                    throw new Error("Unexpected server response — not JSON");
                }

                if (!response.ok) {
                    throw new Error(result.error || 'Submission failed');
                }

                statusEl.textContent = "✅ Message sent successfully!";
                statusEl.className = "form-status success";
                contactForm.reset();

                // Optional: log saved data
                try {
                    const debugResponse = await fetch('/debug-submissions');
                    console.log('Current submissions:', await debugResponse.json());
                } catch (err) {
                    console.warn("Debug fetch failed:", err);
                }

            } catch (error) {
                statusEl.textContent = `❌ Error: ${error.message}`;
                statusEl.className = "form-status error";
                console.error('Submission error:', error);
            }
        });
    }
});
