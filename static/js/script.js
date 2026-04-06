$(document).ready(function() {
    $('#routeForm').submit(function(event) {
        event.preventDefault();
        $('#submitBtn').prop('disabled', true).text('Processing...');
        $('#error').addClass('d-none').text('');
        $('#status').addClass('d-none').text('');
        
        const accidentSite = $('#accident_site').val();
        
        $.ajax({
            url: '/compute_route',
            type: 'POST',
            data: { accident_site: accidentSite },
            success: function(response) {
                console.log("AJAX Response:", response);
                if (response.error) {
                    $('#error').removeClass('d-none').text(response.error);
                } else {
                    $('#status').removeClass('d-none').text('Traffic Status: ' + response.traffic_status);
                    $('#map').html(response.map_html); // Insert map HTML directly
                }
                $('#submitBtn').prop('disabled', false).text('Find Route');
            },
            error: function() {
                $('#error').removeClass('d-none').text('An error occurred. Please try again.');
                $('#submitBtn').prop('disabled', false).text('Find Route');
            }
        });
    });
});