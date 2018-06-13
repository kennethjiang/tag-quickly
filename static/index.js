
$(document).ready(function() {

	$( "#selectable" ).selectable({
	  filter: 'li',
		stop: function() {
			$( "#select-result" ).text(function( index ) {
			  return $('.ui-selected').length;
			});
        }
	});

	$('#select-all').on('click', function () {
		$('.thumbnail').addClass('ui-selected');
	})

    $(document).keydown(function(e) {
        if (e.which == 32) {  // space key
            if (toggleZoomIn()) {
	            e.preventDefault(); // prevent the default action (scroll / move caret)
            }
        }

		if (e.ctrlKey) {
	        if (e.which >= 49 && e.which < 59) {  // Number key 1 - 9
	            var i = e.which - 49;

	            if (i >= all_tags.length) {
	                return;
	            }

	            tagToggled(all_tags[i]);

	            e.preventDefault(); // prevent the default action (scroll / move caret)
	        }
		}
    });

    loadTags();
} );

var all_tags = [];

var tagToggled = function(tagName) {
    var targets = $('.ui-selected').toArray().map(function(el) {return el.id})
    //var verb = $(el).hasClass('active') ? 'DELETE' : 'PUT';  // class has not changed when onclick is called. So having 'active' means 'it's about to become inactive
    $.ajax({
        url: '/api/tags/' + tagName + '/',
        type: 'PUT',
        data: JSON.stringify({targets}),
	    contentType: "application/json; charset=utf-8",
	    dataType: "json",
        success: update_tags,
    })
}

var tagToBadge = function(tag) {
    return '<span class="badge badge-' + all_tags.indexOf(tag) + '">' + tag + '</span>';
}

var update_tags = function(result) {
    all_tags = result.all_tags;
    $('#tag-list').html(all_tags.map(tagToBadge));
    $('li.thumbnail.ui-selectee').each( function(_, el) {
        var tags = result.targets[el.id] || [];
        $(el).find('.caption').html(tags.map(tagToBadge));
    })
}

var loadTags = function() {
    $.ajax({
        url: "/api/tags/",
        type: 'GET',
	    dataType: "json",
        success: update_tags,
    });
}

var toggleZoomIn = function() {
    if ($('#zoom-in-modal').is(':visible')) {
        $('#zoom-in-modal').modal('hide');
        return false;
    }

    var targets = $('.ui-selected').toArray().map(function(el) {return el.id})
	if (targets.length != 1) {
        return false;
    }

    $('#zoom-in-img').attr('src', '/imgs/' + targets[0]);
    $('#zoom-in-modal-label').text(targets[0]);
    $('#zoom-in-modal').modal('show', {keyboard: true});

    return true;
}
