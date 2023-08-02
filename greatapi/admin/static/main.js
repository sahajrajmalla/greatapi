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
  if (!menuBox.style.display || menuBox.style.display == "none") {
    menuBox.style.display = "flex";
  } else {
    menuBox.style.display='';
  }
}

function togglePassword(e) {
  var password = document.getElementById(e)
  var eye = password.parentElement.querySelector('#eye')

  let openSvg = ` <svg xmlns="http://www.w3.org/2000/svg" class="w-6 h-6 stroke-shadeblack" viewBox="0 0 512 512">
    <path
      d="M255.66 112c-77.94 0-157.89 45.11-220.83 135.33a16 16 0 00-.27 17.77C82.92 340.8 161.8 400 255.66 400c92.84 0 173.34-59.38 221.79-135.25a16.14 16.14 0 000-17.47C428.89 172.28 347.8 112 255.66 112z"
      fill="none" stroke-linecap="round" stroke-linejoin="round" stroke-width="40" />
    <circle cx="256" cy="256" r="80" fill="none" stroke-miterlimit="10" stroke-width="40" />
  </svg>`

  password.type = password.type == 'text' ? 'password' : 'text'
  eye.innerHTML = password.type == 'text' ? 'Close' : openSvg

}


function togglePopup(){
  let settingsPopup = document.getElementById('account-identifier')
  settingsPopup.style.display=='none' ? settingsPopup.style.display='flex' : settingsPopup.style.display='none'
  }


  function getCurrentDate(event) {
    let eventParentNode = event.target.parentNode.parentNode
    let date = eventParentNode.querySelector('#date')

    date.value = new Date().toISOString().split('T')[0];
  }

  function getCurrentTime(event) {
    let eventParentNode = event.target.parentNode.parentNode
    let date = eventParentNode.querySelector('#time')
    date.value = new Date().toISOString().split('T')[1].split('.')[0];
  }


function onSelectAll(){
  var table = document.getElementById('item-table')
  var items = table.querySelectorAll('#checkbox')

    for (var i=0; i<items.length; i++){
      items[i].checked = event.target.checked
    }


}
