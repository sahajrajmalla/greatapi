tailwind.config = {
  theme: {
    extend: {
      colors: {
        primary: "#0055FF",
        success: "#3BB200",
        warning: "#FFB731",
        danger: "#FF0000",
        blackone: "#1F232E",
        blacktwo: "#3D414C",
        shadeblack: "#676B77",
        shadegray: "#F7F8FB",
        shadeblue: "#F7FAFF",
      },
      screens: {
        xs: "380px",
        sm: "480px",
        md: "768px",
        lg: "991px",
        xl: "1050px",
        xxl: "1600px",
      },
    },
  },
};

function toggleMenu() {
  var menuBox = document.getElementById("menu-box");
  if (menuBox.style.display == "none") {
    menuBox.style.display = "flex";
  } else {
    menuBox.style.display = "none";
  }
}
