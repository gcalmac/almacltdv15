odoo.define("website_multi_image.carousel", function (require) {
  "use strict";
  var publicWidget = require("web.public.widget");

  function changeFirst(isHover) {
      
    if (isHover) {
        document.getElementById('first').style.backgroundImage = "url('x.jpeg')";
    } else {
        document.getElementById('first').style.backgroundImage = "url('images.jpeg')";
    }
}


  publicWidget.registry.ProductCarousel = publicWidget.Widget.extend({
    selector: "#o-carousel-product",
    events: {
      "click li": "_onChangeItem",
      "click .carousel-control-next": "_nextItem",
      "click .carousel-control-prev": "_prevItem",
    },

    start: function () {
      $("#o-carousel-product .owl-carousel").css("opacity", 1);
      $("#o-carousel-product .owl-carousel").owlCarousel({
        loop: true,
        dots: false,
        nav: false,
        responsive: {
          0: {
            items: 3,
          },
          576: {
            items: 4,
          },
          786: {
            items: 9,
          },
          992: {
            items: 7,
          },
          1200: {
            items: 9,
          },
        },
      });
    },

    _onChangeItem: function (ev) {
      $(ev.target).closest("li").addClass("active", 10);
    },

    _nextItem: function (ev) {
      var carousel;
      var carousel_obj = $(ev.delegateTarget)
        .find(".carousel-inner div.active")
        .next();
      if (carousel_obj.length != 0) {
        carousel = carousel_obj.attr("value");
      } else {
        carousel = $(ev.delegateTarget)
          .find(".carousel-inner>div")
          .attr("value");
      }
      $(".carousel-indicators [value=" + carousel + "]")
        .closest("li")
        .addClass("active", 100);
      var _nextslide = parseInt(
        $(".carousel-indicators [value=" + carousel + "]")
          .closest("li")
          .attr("data-slide-to")
      );
      $(".carousel-indicators").trigger("to.owl.carousel", _nextslide);
    },

    _prevItem: function (ev) {
      var carousel;
      var carousel_obj = $(ev.delegateTarget)
        .find(".carousel-inner div.active")
        .prev();
      if (carousel_obj.length != 0) {
        carousel = carousel_obj.attr("value");
      } else {
        carousel = $(ev.delegateTarget)
          .find(".carousel-inner> div:last-child")
          .attr("value");
      }
      $(".carousel-indicators [value=" + carousel + "]")
        .closest("li")
        .addClass("active", 100);
      var _prevslide = parseInt(
        $(".carousel-indicators [value=" + carousel + "]")
          .closest("li")
          .attr("data-slide-to")
      );
      $(".carousel-indicators").trigger("to.owl.carousel", _prevslide);
    },
  });
});
