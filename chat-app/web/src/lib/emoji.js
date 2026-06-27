// Catálogo de emojis para el selector de reacciones, agrupado por categoría.
// Sin dependencias externas (prioridad: ligereza). Cada grupo tiene un icono
// Tabler para la pestaña y una lista de emojis. El mapa `keywords` da términos
// de búsqueda en español para un subconjunto frecuente; los que no tengan
// keyword simplemente no aparecen al buscar, pero sí en su categoría.

export const GROUPS = [
  {
    id: "caras",
    icon: "ti-mood-smile",
    label: "Caras y emociones",
    emojis: [
      "😀","😃","😄","😁","😆","😅","🤣","😂","🙂","🙃","🫠","😉","😊","😇",
      "🥰","😍","🤩","😘","😗","😚","😙","🥲","😋","😛","😜","🤪","😝","🤑",
      "🤗","🤭","🫢","🫣","🤫","🤔","🫡","🤐","🤨","😐","😑","😶","🫥","😏",
      "😒","🙄","😬","😮‍💨","🤥","😌","😔","😪","🤤","😴","😷","🤒","🤕","🤢",
      "🤮","🤧","🥵","🥶","🥴","😵","😵‍💫","🤯","🤠","🥳","🥸","😎","🤓","🧐",
      "😕","🫤","😟","🙁","☹️","😮","😯","😲","😳","🥺","🥹","😦","😧","😨",
      "😰","😥","😢","😭","😱","😖","😣","😞","😓","😩","😫","🥱","😤","😡",
      "😠","🤬","😈","👿","💀","☠️","💩","🤡","👹","👺","👻","👽","👾","🤖",
    ],
  },
  {
    id: "gestos",
    icon: "ti-hand-stop",
    label: "Gestos y personas",
    emojis: [
      "👍","👎","👌","🤌","🤏","✌️","🤞","🫰","🤟","🤘","🤙","👈","👉","👆",
      "👇","☝️","🫵","✋","🤚","🖐️","🖖","👋","🤝","🙏","✍️","💅","🤳","💪",
      "🦾","🖕","👏","🙌","🫶","👐","🤲","🤜","🤛","✊","👊","🫳","🫴","🦵",
      "🦶","👂","🦻","👃","🧠","🫀","🫁","🦷","🦴","👀","👁️","👅","👄","🫦",
      "👶","🧒","👦","👧","🧑","👨","👩","🧔","👴","👵","🙇","💁","🙅","🙆",
      "🤷","🤦","🙋","🧏","🙎","🙍","💇","💆","🧖","💃","🕺","👯","🚶","🏃",
    ],
  },
  {
    id: "corazones",
    icon: "ti-heart",
    label: "Corazones y símbolos",
    emojis: [
      "❤️","🧡","💛","💚","💙","💜","🖤","🤍","🤎","💔","❤️‍🔥","❤️‍🩹","💕","💞",
      "💓","💗","💖","💘","💝","💟","♥️","💌","💋","💯","💢","💥","💫","💦",
      "💨","🕳️","💬","💭","🗯️","♨️","✨","⭐","🌟","⚡","🔥","🌈","☀️",
      "✅","❌","❎","➕","➖","✖️","♾️","‼️","⁉️","❓","❔","❕","❗","〰️",
      "🔴","🟠","🟡","🟢","🔵","🟣","🟤","⚫","⚪","🟥","🟧","🟨","🟩","🟦",
    ],
  },
  {
    id: "animales",
    icon: "ti-paw",
    label: "Animales y naturaleza",
    emojis: [
      "🐶","🐱","🐭","🐹","🐰","🦊","🐻","🐼","🐨","🐯","🦁","🐮","🐷","🐸",
      "🐵","🙈","🙉","🙊","🐔","🐧","🐦","🐤","🦆","🦅","🦉","🦇","🐺","🐗",
      "🐴","🦄","🐝","🪲","🐛","🦋","🐌","🐞","🐜","🦗","🕷️","🦂","🐢","🐍",
      "🦎","🐙","🦑","🦐","🦀","🐡","🐠","🐟","🐬","🐳","🐋","🦈","🐊","🐅",
      "🌵","🎄","🌲","🌳","🌴","🪴","🌱","🌿","☘️","🍀","🎍","🍃","🍂","🍁",
      "🌷","🌹","🥀","🌺","🌸","🌼","🌻","🌞","🌝","🌚","🌑","🌙","⭐","🌍",
    ],
  },
  {
    id: "comida",
    icon: "ti-pizza",
    label: "Comida y bebida",
    emojis: [
      "🍎","🍐","🍊","🍋","🍌","🍉","🍇","🍓","🫐","🍈","🍒","🍑","🥭","🍍",
      "🥥","🥝","🍅","🍆","🥑","🥦","🥬","🥒","🌶️","🫑","🌽","🥕","🧄","🧅",
      "🥔","🍠","🥐","🥯","🍞","🥖","🧀","🥚","🍳","🧈","🥞","🧇","🥓","🍔",
      "🍟","🍕","🌭","🥪","🌮","🌯","🥙","🧆","🥘","🍝","🍜","🍲","🍛","🍣",
      "🍱","🥟","🍤","🍙","🍚","🍘","🍥","🥠","🍢","🍡","🍧","🍨","🍦","🥧",
      "🧁","🍰","🎂","🍮","🍭","🍬","🍫","🍿","🍩","🍪","🌰","☕","🍵","🍺",
      "🍻","🥂","🍷","🥃","🍸","🍹","🧉","🥤","🧋","🧃","🍾","🥛","🧊","🍴",
    ],
  },
  {
    id: "actividad",
    icon: "ti-ball-football",
    label: "Actividades y deporte",
    emojis: [
      "⚽","🏀","🏈","⚾","🥎","🎾","🏐","🏉","🥏","🎱","🪀","🏓","🏸","🏒",
      "🏑","🥍","🏏","🥅","⛳","🪁","🏹","🎣","🤿","🥊","🥋","🎽","🛹","🛼",
      "🛷","⛸️","🥌","🎿","⛷️","🏂","🏋️","🤼","🤸","⛹️","🤺","🤾","🏌️","🏇",
      "🧘","🏄","🏊","🤽","🚣","🧗","🚵","🚴","🏆","🥇","🥈","🥉","🏅","🎖️",
      "🎫","🎟️","🎪","🤹","🎭","🩰","🎨","🎬","🎤","🎧","🎼","🎹","🥁","🎷",
      "🎺","🎸","🪕","🎻","🎲","♟️","🎯","🎳","🎮","🎰","🧩","🎉","🎊","🎈",
    ],
  },
  {
    id: "viajes",
    icon: "ti-car",
    label: "Viajes y lugares",
    emojis: [
      "🚗","🚕","🚙","🚌","🚎","🏎️","🚓","🚑","🚒","🚐","🛻","🚚","🚛","🚜",
      "🏍️","🛵","🚲","🛴","🚨","🚔","🚍","🚘","🚖","🚡","🚠","🚟","🚃","🚋",
      "🚝","🚄","🚅","🚈","🚂","🚆","🚇","🚊","🚉","✈️","🛫","🛬","🛩️","💺",
      "🚀","🛸","🚁","🛶","⛵","🚤","🛥️","🛳️","⛴️","🚢","⚓","🗺️","🗿","🗽",
      "🗼","🏰","🏯","🏟️","🎡","🎢","🎠","⛲","⛱️","🏖️","🏝️","🏜️","🌋","⛰️",
      "🏔️","🗻","🏕️","⛺","🏠","🏡","🏘️","🏚️","🏗️","🏢","🏬","🏣","🏤","🏥",
    ],
  },
  {
    id: "objetos",
    icon: "ti-bulb",
    label: "Objetos",
    emojis: [
      "⌚","📱","💻","⌨️","🖥️","🖨️","🖱️","💽","💾","💿","📀","📷","📸","📹",
      "🎥","📞","☎️","📟","📠","📺","📻","🎙️","⏱️","⏰","🕰️","⌛","⏳","📡",
      "🔋","🔌","💡","🔦","🕯️","🧯","🛢️","💸","💵","💴","💶","💷","🪙","💰",
      "💳","💎","⚖️","🪜","🧰","🔧","🔨","⚒️","🛠️","⛏️","🔩","⚙️","🧱","⛓️",
      "🔫","💣","🪓","🔪","🗡️","⚔️","🛡️","🚬","⚰️","🪦","🏺","🔮","📿","🧿",
      "💈","🔭","🔬","🕳️","💊","💉","🩸","🩹","🩺","🌡️","🧬","🦠","🧫","🧪",
      "📔","📕","📖","📗","📘","📙","📚","📓","📒","📃","📜","📄","📰","🗞️",
      "📑","🔖","🏷️","✉️","📧","📨","📩","📤","📥","📦","📫","📮","📝","✏️",
    ],
  },
  {
    id: "banderas",
    icon: "ti-flag",
    label: "Banderas",
    emojis: [
      "🏁","🚩","🎌","🏴","🏳️","🏳️‍🌈","🏳️‍⚧️","🏴‍☠️","🇪🇸","🇲🇽","🇦🇷","🇨🇴","🇨🇱","🇵🇪",
      "🇻🇪","🇺🇾","🇪🇨","🇧🇴","🇵🇾","🇨🇷","🇵🇦","🇬🇹","🇩🇴","🇨🇺","🇺🇸","🇬🇧","🇫🇷","🇩🇪",
      "🇮🇹","🇵🇹","🇧🇷","🇯🇵","🇰🇷","🇨🇳","🇮🇳","🇷🇺","🇨🇦","🇦🇺","🇳🇱","🇧🇪","🇨🇭","🇸🇪",
    ],
  },
];

// Términos de búsqueda en español -> emoji. Cubre los más usados.
export const KEYWORDS = {
  "😀": "feliz sonrisa cara", "😃": "feliz sonrisa", "😄": "feliz risa",
  "😁": "sonrisa dientes", "😆": "risa carcajada", "😅": "risa nervios sudor",
  "🤣": "risa suelo lol", "😂": "risa llanto lol jaja", "🙂": "sonrisa leve",
  "🙃": "al reves ironia", "😉": "guiño coqueto", "😊": "feliz tierno",
  "😍": "amor enamorado ojos corazon", "🥰": "amor enamorado tierno",
  "😘": "beso amor", "😗": "beso", "😋": "rico delicioso lengua", "😛": "lengua burla",
  "😜": "lengua guiño broma", "🤪": "loco broma", "🤔": "pensando duda",
  "🤨": "ceja duda escepticismo", "😐": "neutral serio", "😑": "inexpresivo",
  "😶": "sin palabras silencio", "🙄": "ojos blanco fastidio", "😏": "picaro",
  "😴": "dormido sueño", "😪": "sueño cansado", "🤤": "baba antojo",
  "😎": "genial gafas cool", "🤓": "nerd lentes", "🥳": "fiesta celebracion",
  "😮": "sorpresa asombro wow", "😯": "sorpresa", "😲": "asombro shock",
  "😳": "verguenza sonrojo", "🥺": "suplica tierno ojitos", "🥹": "emocion lagrimas",
  "😢": "triste llanto lagrima", "😭": "llorando triste mucho", "😱": "miedo grito susto",
  "😡": "enojado rabia furia", "😠": "enojado molesto", "🤬": "groseria insulto enojo",
  "😈": "diablo travieso", "💀": "muerte calavera", "💩": "caca popo",
  "🤡": "payaso", "👻": "fantasma halloween", "👽": "alien extraterrestre",
  "🤖": "robot bot", "🎃": "calabaza halloween",
  "👍": "bien like aprobado pulgar arriba ok si", "👎": "mal dislike pulgar abajo no",
  "👌": "ok perfecto", "✌️": "paz victoria", "🤞": "suerte dedos cruzados",
  "🤟": "te quiero", "🤘": "rock cuernos", "🤙": "llamame", "👏": "aplauso bravo",
  "🙌": "celebracion manos arriba", "🙏": "gracias rezar porfavor suplica",
  "💪": "fuerza musculo brazo", "🖕": "dedo grosero", "👋": "hola adios saludo",
  "🤝": "trato acuerdo apreton", "✊": "puño fuerza", "👊": "puño golpe",
  "❤️": "amor corazon rojo", "🧡": "corazon naranja", "💛": "corazon amarillo",
  "💚": "corazon verde", "💙": "corazon azul", "💜": "corazon morado",
  "🖤": "corazon negro", "🤍": "corazon blanco", "💔": "corazon roto desamor",
  "❤️‍🔥": "corazon fuego pasion", "💕": "corazones amor", "💖": "corazon brillante amor",
  "💯": "cien perfecto total", "💥": "explosion boom", "✨": "brillo magia estrellas",
  "🔥": "fuego genial fire", "⭐": "estrella", "🌈": "arcoiris",
  "✅": "check si correcto bien", "❌": "no error mal cruz", "❗": "exclamacion importante",
  "❓": "pregunta duda", "🎉": "fiesta celebracion confeti", "🎊": "fiesta confeti",
  "🎈": "globo fiesta", "🎁": "regalo", "🐶": "perro", "🐱": "gato",
  "🦊": "zorro", "🐻": "oso", "🐼": "panda", "🦁": "leon", "🐸": "rana",
  "🐵": "mono", "🦄": "unicornio", "🐝": "abeja", "🦋": "mariposa",
  "🍎": "manzana fruta", "🍌": "platano banana", "🍓": "fresa", "🍕": "pizza",
  "🍔": "hamburguesa", "🍟": "papas fritas", "🌮": "taco", "🍣": "sushi",
  "🍰": "pastel torta", "🎂": "cumpleaños pastel torta", "🍫": "chocolate",
  "🍿": "palomitas", "☕": "cafe", "🍺": "cerveza", "🍻": "cervezas brindis",
  "🥂": "brindis copas champan", "🍷": "vino copa", "⚽": "futbol balon",
  "🏀": "basquet baloncesto", "🎮": "videojuego gaming control", "🎸": "guitarra musica",
  "🎧": "audifonos musica", "🎵": "musica nota", "🚗": "carro coche auto",
  "✈️": "avion viaje vuelo", "🚀": "cohete espacio lanzamiento", "💻": "computadora laptop",
  "📱": "celular telefono movil", "💡": "idea bombilla", "💰": "dinero plata",
  "💎": "diamante joya", "🔫": "pistola arma", "⚔️": "espadas pelea", "📚": "libros estudio",
  "✏️": "lapiz escribir", "💊": "pastilla medicina", "🇪🇸": "españa bandera",
  "🇲🇽": "mexico bandera", "🇨🇴": "colombia bandera", "🇦🇷": "argentina bandera",
};

// Emojis usados con más frecuencia (fila de acceso rápido).
export const FREQUENT = ["👍","❤️","😂","🎉","😮","😢","🔥","🙏","👏","😍","💯","✅"];

const _all = GROUPS.flatMap((g) => g.emojis);

export function searchEmojis(query) {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  const out = [];
  for (const e of _all) {
    const kw = KEYWORDS[e];
    if (kw && kw.includes(q)) out.push(e);
  }
  return out;
}
