/******/ (function(modules) { // webpackBootstrap
/******/ 	// The module cache
/******/ 	var installedModules = {};
/******/
/******/ 	// The require function
/******/ 	function __webpack_require__(moduleId) {
/******/
/******/ 		// Check if module is in cache
/******/ 		if(installedModules[moduleId]) {
/******/ 			return installedModules[moduleId].exports;
/******/ 		}
/******/ 		// Create a new module (and put it into the cache)
/******/ 		var module = installedModules[moduleId] = {
/******/ 			i: moduleId,
/******/ 			l: false,
/******/ 			exports: {}
/******/ 		};
/******/
/******/ 		// Execute the module function
/******/ 		modules[moduleId].call(module.exports, module, module.exports, __webpack_require__);
/******/
/******/ 		// Flag the module as loaded
/******/ 		module.l = true;
/******/
/******/ 		// Return the exports of the module
/******/ 		return module.exports;
/******/ 	}
/******/
/******/
/******/ 	// expose the modules object (__webpack_modules__)
/******/ 	__webpack_require__.m = modules;
/******/
/******/ 	// expose the module cache
/******/ 	__webpack_require__.c = installedModules;
/******/
/******/ 	// define getter function for harmony exports
/******/ 	__webpack_require__.d = function(exports, name, getter) {
/******/ 		if(!__webpack_require__.o(exports, name)) {
/******/ 			Object.defineProperty(exports, name, { enumerable: true, get: getter });
/******/ 		}
/******/ 	};
/******/
/******/ 	// define __esModule on exports
/******/ 	__webpack_require__.r = function(exports) {
/******/ 		if(typeof Symbol !== 'undefined' && Symbol.toStringTag) {
/******/ 			Object.defineProperty(exports, Symbol.toStringTag, { value: 'Module' });
/******/ 		}
/******/ 		Object.defineProperty(exports, '__esModule', { value: true });
/******/ 	};
/******/
/******/ 	// create a fake namespace object
/******/ 	// mode & 1: value is a module id, require it
/******/ 	// mode & 2: merge all properties of value into the ns
/******/ 	// mode & 4: return value when already ns object
/******/ 	// mode & 8|1: behave like require
/******/ 	__webpack_require__.t = function(value, mode) {
/******/ 		if(mode & 1) value = __webpack_require__(value);
/******/ 		if(mode & 8) return value;
/******/ 		if((mode & 4) && typeof value === 'object' && value && value.__esModule) return value;
/******/ 		var ns = Object.create(null);
/******/ 		__webpack_require__.r(ns);
/******/ 		Object.defineProperty(ns, 'default', { enumerable: true, value: value });
/******/ 		if(mode & 2 && typeof value != 'string') for(var key in value) __webpack_require__.d(ns, key, function(key) { return value[key]; }.bind(null, key));
/******/ 		return ns;
/******/ 	};
/******/
/******/ 	// getDefaultExport function for compatibility with non-harmony modules
/******/ 	__webpack_require__.n = function(module) {
/******/ 		var getter = module && module.__esModule ?
/******/ 			function getDefault() { return module['default']; } :
/******/ 			function getModuleExports() { return module; };
/******/ 		__webpack_require__.d(getter, 'a', getter);
/******/ 		return getter;
/******/ 	};
/******/
/******/ 	// Object.prototype.hasOwnProperty.call
/******/ 	__webpack_require__.o = function(object, property) { return Object.prototype.hasOwnProperty.call(object, property); };
/******/
/******/ 	// __webpack_public_path__
/******/ 	__webpack_require__.p = "";
/******/
/******/
/******/ 	// Load entry module and return exports
/******/ 	return __webpack_require__(__webpack_require__.s = 18);
/******/ })
/************************************************************************/
/******/ ([
/* 0 */,
/* 1 */
/*!****************************!*\
  !*** ./Src/Tool/Logger.js ***!
  \****************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* harmony import */ var _Time__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! ./Time */ 2);
function _typeof(o) { "@babel/helpers - typeof"; return _typeof = "function" == typeof Symbol && "symbol" == typeof Symbol.iterator ? function (o) { return typeof o; } : function (o) { return o && "function" == typeof Symbol && o.constructor === Symbol && o !== Symbol.prototype ? "symbol" : typeof o; }, _typeof(o); }
function _toConsumableArray(r) { return _arrayWithoutHoles(r) || _iterableToArray(r) || _unsupportedIterableToArray(r) || _nonIterableSpread(); }
function _nonIterableSpread() { throw new TypeError("Invalid attempt to spread non-iterable instance.\nIn order to be iterable, non-array objects must have a [Symbol.iterator]() method."); }
function _unsupportedIterableToArray(r, a) { if (r) { if ("string" == typeof r) return _arrayLikeToArray(r, a); var t = {}.toString.call(r).slice(8, -1); return "Object" === t && r.constructor && (t = r.constructor.name), "Map" === t || "Set" === t ? Array.from(r) : "Arguments" === t || /^(?:Ui|I)nt(?:8|16|32)(?:Clamped)?Array$/.test(t) ? _arrayLikeToArray(r, a) : void 0; } }
function _iterableToArray(r) { if ("undefined" != typeof Symbol && null != r[Symbol.iterator] || null != r["@@iterator"]) return Array.from(r); }
function _arrayWithoutHoles(r) { if (Array.isArray(r)) return _arrayLikeToArray(r); }
function _arrayLikeToArray(r, a) { (null == a || a > r.length) && (a = r.length); for (var e = 0, n = Array(a); e < a; e++) n[e] = r[e]; return n; }
function _classCallCheck(a, n) { if (!(a instanceof n)) throw new TypeError("Cannot call a class as a function"); }
function _defineProperties(e, r) { for (var t = 0; t < r.length; t++) { var o = r[t]; o.enumerable = o.enumerable || !1, o.configurable = !0, "value" in o && (o.writable = !0), Object.defineProperty(e, _toPropertyKey(o.key), o); } }
function _createClass(e, r, t) { return r && _defineProperties(e.prototype, r), t && _defineProperties(e, t), Object.defineProperty(e, "prototype", { writable: !1 }), e; }
function _toPropertyKey(t) { var i = _toPrimitive(t, "string"); return "symbol" == _typeof(i) ? i : i + ""; }
function _toPrimitive(t, r) { if ("object" != _typeof(t) || !t) return t; var e = t[Symbol.toPrimitive]; if (void 0 !== e) { var i = e.call(t, r || "default"); if ("object" != _typeof(i)) return i; throw new TypeError("@@toPrimitive must return a primitive value."); } return ("string" === r ? String : Number)(t); }

var Logger = /*#__PURE__*/function () {
  function Logger() {
    _classCallCheck(this, Logger);
    this.enableDebug = false;
  }
  return _createClass(Logger, [{
    key: "_Format",
    value: function _Format(args) {
      return ["[".concat(Object(_Time__WEBPACK_IMPORTED_MODULE_0__["FormatDate"])(new Date()), "]")].concat(args);
    }
  }, {
    key: "SetEnableDebug",
    value: function SetEnableDebug(enable) {
      this.enableDebug = enable;
    }
  }, {
    key: "Debug",
    value: function Debug() {
      if (this.enableDebug) {
        var _console;
        for (var _len = arguments.length, args = new Array(_len), _key = 0; _key < _len; _key++) {
          args[_key] = arguments[_key];
        }
        (_console = console).debug.apply(_console, _toConsumableArray(this._Format(args)));
      }
    }
  }, {
    key: "Info",
    value: function Info() {
      var _console2;
      for (var _len2 = arguments.length, args = new Array(_len2), _key2 = 0; _key2 < _len2; _key2++) {
        args[_key2] = arguments[_key2];
      }
      (_console2 = console).log.apply(_console2, _toConsumableArray(this._Format(args)));
    }
  }, {
    key: "Warn",
    value: function Warn() {
      var _console3;
      for (var _len3 = arguments.length, args = new Array(_len3), _key3 = 0; _key3 < _len3; _key3++) {
        args[_key3] = arguments[_key3];
      }
      (_console3 = console).warn.apply(_console3, _toConsumableArray(this._Format(args)));
    }
  }, {
    key: "Error",
    value: function Error() {
      var _console4;
      for (var _len4 = arguments.length, args = new Array(_len4), _key4 = 0; _key4 < _len4; _key4++) {
        args[_key4] = arguments[_key4];
      }
      (_console4 = console).error.apply(_console4, _toConsumableArray(this._Format(args)));
    }
  }]);
}();
var logger = new Logger();
/* harmony default export */ __webpack_exports__["default"] = (logger);

/***/ }),
/* 2 */
/*!**************************!*\
  !*** ./Src/Tool/Time.js ***!
  \**************************/
/*! exports provided: FormatDate */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "FormatDate", function() { return FormatDate; });
function FormatDate(date) {
  return "".concat(date.getFullYear(), "-").concat((date.getMonth() + 1).toString().padStart(2, '0'), "-").concat(date.getDate().toString().padStart(2, '0'), " ").concat(date.getHours().toString().padStart(2, '0'), ":").concat(date.getMinutes().toString().padStart(2, '0'), ":").concat(date.getSeconds().toString().padStart(2, '0'), ",").concat(date.getMilliseconds().toString().padStart(3, '0'));
}

/***/ }),
/* 3 */
/*!**********************************!*\
  !*** ./Src/Tool/BrowserTools.js ***!
  \**********************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* harmony import */ var _StringTools__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! ./StringTools */ 4);
/* harmony import */ var _Logger__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(/*! ./Logger */ 1);
function _typeof(o) { "@babel/helpers - typeof"; return _typeof = "function" == typeof Symbol && "symbol" == typeof Symbol.iterator ? function (o) { return typeof o; } : function (o) { return o && "function" == typeof Symbol && o.constructor === Symbol && o !== Symbol.prototype ? "symbol" : typeof o; }, _typeof(o); }
function _regeneratorRuntime() { "use strict"; /*! regenerator-runtime -- Copyright (c) 2014-present, Facebook, Inc. -- license (MIT): https://github.com/facebook/regenerator/blob/main/LICENSE */ _regeneratorRuntime = function _regeneratorRuntime() { return e; }; var t, e = {}, r = Object.prototype, n = r.hasOwnProperty, o = Object.defineProperty || function (t, e, r) { t[e] = r.value; }, i = "function" == typeof Symbol ? Symbol : {}, a = i.iterator || "@@iterator", c = i.asyncIterator || "@@asyncIterator", u = i.toStringTag || "@@toStringTag"; function define(t, e, r) { return Object.defineProperty(t, e, { value: r, enumerable: !0, configurable: !0, writable: !0 }), t[e]; } try { define({}, ""); } catch (t) { define = function define(t, e, r) { return t[e] = r; }; } function wrap(t, e, r, n) { var i = e && e.prototype instanceof Generator ? e : Generator, a = Object.create(i.prototype), c = new Context(n || []); return o(a, "_invoke", { value: makeInvokeMethod(t, r, c) }), a; } function tryCatch(t, e, r) { try { return { type: "normal", arg: t.call(e, r) }; } catch (t) { return { type: "throw", arg: t }; } } e.wrap = wrap; var h = "suspendedStart", l = "suspendedYield", f = "executing", s = "completed", y = {}; function Generator() {} function GeneratorFunction() {} function GeneratorFunctionPrototype() {} var p = {}; define(p, a, function () { return this; }); var d = Object.getPrototypeOf, v = d && d(d(values([]))); v && v !== r && n.call(v, a) && (p = v); var g = GeneratorFunctionPrototype.prototype = Generator.prototype = Object.create(p); function defineIteratorMethods(t) { ["next", "throw", "return"].forEach(function (e) { define(t, e, function (t) { return this._invoke(e, t); }); }); } function AsyncIterator(t, e) { function invoke(r, o, i, a) { var c = tryCatch(t[r], t, o); if ("throw" !== c.type) { var u = c.arg, h = u.value; return h && "object" == _typeof(h) && n.call(h, "__await") ? e.resolve(h.__await).then(function (t) { invoke("next", t, i, a); }, function (t) { invoke("throw", t, i, a); }) : e.resolve(h).then(function (t) { u.value = t, i(u); }, function (t) { return invoke("throw", t, i, a); }); } a(c.arg); } var r; o(this, "_invoke", { value: function value(t, n) { function callInvokeWithMethodAndArg() { return new e(function (e, r) { invoke(t, n, e, r); }); } return r = r ? r.then(callInvokeWithMethodAndArg, callInvokeWithMethodAndArg) : callInvokeWithMethodAndArg(); } }); } function makeInvokeMethod(e, r, n) { var o = h; return function (i, a) { if (o === f) throw Error("Generator is already running"); if (o === s) { if ("throw" === i) throw a; return { value: t, done: !0 }; } for (n.method = i, n.arg = a;;) { var c = n.delegate; if (c) { var u = maybeInvokeDelegate(c, n); if (u) { if (u === y) continue; return u; } } if ("next" === n.method) n.sent = n._sent = n.arg;else if ("throw" === n.method) { if (o === h) throw o = s, n.arg; n.dispatchException(n.arg); } else "return" === n.method && n.abrupt("return", n.arg); o = f; var p = tryCatch(e, r, n); if ("normal" === p.type) { if (o = n.done ? s : l, p.arg === y) continue; return { value: p.arg, done: n.done }; } "throw" === p.type && (o = s, n.method = "throw", n.arg = p.arg); } }; } function maybeInvokeDelegate(e, r) { var n = r.method, o = e.iterator[n]; if (o === t) return r.delegate = null, "throw" === n && e.iterator["return"] && (r.method = "return", r.arg = t, maybeInvokeDelegate(e, r), "throw" === r.method) || "return" !== n && (r.method = "throw", r.arg = new TypeError("The iterator does not provide a '" + n + "' method")), y; var i = tryCatch(o, e.iterator, r.arg); if ("throw" === i.type) return r.method = "throw", r.arg = i.arg, r.delegate = null, y; var a = i.arg; return a ? a.done ? (r[e.resultName] = a.value, r.next = e.nextLoc, "return" !== r.method && (r.method = "next", r.arg = t), r.delegate = null, y) : a : (r.method = "throw", r.arg = new TypeError("iterator result is not an object"), r.delegate = null, y); } function pushTryEntry(t) { var e = { tryLoc: t[0] }; 1 in t && (e.catchLoc = t[1]), 2 in t && (e.finallyLoc = t[2], e.afterLoc = t[3]), this.tryEntries.push(e); } function resetTryEntry(t) { var e = t.completion || {}; e.type = "normal", delete e.arg, t.completion = e; } function Context(t) { this.tryEntries = [{ tryLoc: "root" }], t.forEach(pushTryEntry, this), this.reset(!0); } function values(e) { if (e || "" === e) { var r = e[a]; if (r) return r.call(e); if ("function" == typeof e.next) return e; if (!isNaN(e.length)) { var o = -1, i = function next() { for (; ++o < e.length;) if (n.call(e, o)) return next.value = e[o], next.done = !1, next; return next.value = t, next.done = !0, next; }; return i.next = i; } } throw new TypeError(_typeof(e) + " is not iterable"); } return GeneratorFunction.prototype = GeneratorFunctionPrototype, o(g, "constructor", { value: GeneratorFunctionPrototype, configurable: !0 }), o(GeneratorFunctionPrototype, "constructor", { value: GeneratorFunction, configurable: !0 }), GeneratorFunction.displayName = define(GeneratorFunctionPrototype, u, "GeneratorFunction"), e.isGeneratorFunction = function (t) { var e = "function" == typeof t && t.constructor; return !!e && (e === GeneratorFunction || "GeneratorFunction" === (e.displayName || e.name)); }, e.mark = function (t) { return Object.setPrototypeOf ? Object.setPrototypeOf(t, GeneratorFunctionPrototype) : (t.__proto__ = GeneratorFunctionPrototype, define(t, u, "GeneratorFunction")), t.prototype = Object.create(g), t; }, e.awrap = function (t) { return { __await: t }; }, defineIteratorMethods(AsyncIterator.prototype), define(AsyncIterator.prototype, c, function () { return this; }), e.AsyncIterator = AsyncIterator, e.async = function (t, r, n, o, i) { void 0 === i && (i = Promise); var a = new AsyncIterator(wrap(t, r, n, o), i); return e.isGeneratorFunction(r) ? a : a.next().then(function (t) { return t.done ? t.value : a.next(); }); }, defineIteratorMethods(g), define(g, u, "Generator"), define(g, a, function () { return this; }), define(g, "toString", function () { return "[object Generator]"; }), e.keys = function (t) { var e = Object(t), r = []; for (var n in e) r.push(n); return r.reverse(), function next() { for (; r.length;) { var t = r.pop(); if (t in e) return next.value = t, next.done = !1, next; } return next.done = !0, next; }; }, e.values = values, Context.prototype = { constructor: Context, reset: function reset(e) { if (this.prev = 0, this.next = 0, this.sent = this._sent = t, this.done = !1, this.delegate = null, this.method = "next", this.arg = t, this.tryEntries.forEach(resetTryEntry), !e) for (var r in this) "t" === r.charAt(0) && n.call(this, r) && !isNaN(+r.slice(1)) && (this[r] = t); }, stop: function stop() { this.done = !0; var t = this.tryEntries[0].completion; if ("throw" === t.type) throw t.arg; return this.rval; }, dispatchException: function dispatchException(e) { if (this.done) throw e; var r = this; function handle(n, o) { return a.type = "throw", a.arg = e, r.next = n, o && (r.method = "next", r.arg = t), !!o; } for (var o = this.tryEntries.length - 1; o >= 0; --o) { var i = this.tryEntries[o], a = i.completion; if ("root" === i.tryLoc) return handle("end"); if (i.tryLoc <= this.prev) { var c = n.call(i, "catchLoc"), u = n.call(i, "finallyLoc"); if (c && u) { if (this.prev < i.catchLoc) return handle(i.catchLoc, !0); if (this.prev < i.finallyLoc) return handle(i.finallyLoc); } else if (c) { if (this.prev < i.catchLoc) return handle(i.catchLoc, !0); } else { if (!u) throw Error("try statement without catch or finally"); if (this.prev < i.finallyLoc) return handle(i.finallyLoc); } } } }, abrupt: function abrupt(t, e) { for (var r = this.tryEntries.length - 1; r >= 0; --r) { var o = this.tryEntries[r]; if (o.tryLoc <= this.prev && n.call(o, "finallyLoc") && this.prev < o.finallyLoc) { var i = o; break; } } i && ("break" === t || "continue" === t) && i.tryLoc <= e && e <= i.finallyLoc && (i = null); var a = i ? i.completion : {}; return a.type = t, a.arg = e, i ? (this.method = "next", this.next = i.finallyLoc, y) : this.complete(a); }, complete: function complete(t, e) { if ("throw" === t.type) throw t.arg; return "break" === t.type || "continue" === t.type ? this.next = t.arg : "return" === t.type ? (this.rval = this.arg = t.arg, this.method = "return", this.next = "end") : "normal" === t.type && e && (this.next = e), y; }, finish: function finish(t) { for (var e = this.tryEntries.length - 1; e >= 0; --e) { var r = this.tryEntries[e]; if (r.finallyLoc === t) return this.complete(r.completion, r.afterLoc), resetTryEntry(r), y; } }, "catch": function _catch(t) { for (var e = this.tryEntries.length - 1; e >= 0; --e) { var r = this.tryEntries[e]; if (r.tryLoc === t) { var n = r.completion; if ("throw" === n.type) { var o = n.arg; resetTryEntry(r); } return o; } } throw Error("illegal catch attempt"); }, delegateYield: function delegateYield(e, r, n) { return this.delegate = { iterator: values(e), resultName: r, nextLoc: n }, "next" === this.method && (this.arg = t), y; } }, e; }
function asyncGeneratorStep(n, t, e, r, o, a, c) { try { var i = n[a](c), u = i.value; } catch (n) { return void e(n); } i.done ? t(u) : Promise.resolve(u).then(r, o); }
function _asyncToGenerator(n) { return function () { var t = this, e = arguments; return new Promise(function (r, o) { var a = n.apply(t, e); function _next(n) { asyncGeneratorStep(a, r, o, _next, _throw, "next", n); } function _throw(n) { asyncGeneratorStep(a, r, o, _next, _throw, "throw", n); } _next(void 0); }); }; }
function _createForOfIteratorHelper(r, e) { var t = "undefined" != typeof Symbol && r[Symbol.iterator] || r["@@iterator"]; if (!t) { if (Array.isArray(r) || (t = _unsupportedIterableToArray(r)) || e && r && "number" == typeof r.length) { t && (r = t); var _n = 0, F = function F() {}; return { s: F, n: function n() { return _n >= r.length ? { done: !0 } : { done: !1, value: r[_n++] }; }, e: function e(r) { throw r; }, f: F }; } throw new TypeError("Invalid attempt to iterate non-iterable instance.\nIn order to be iterable, non-array objects must have a [Symbol.iterator]() method."); } var o, a = !0, u = !1; return { s: function s() { t = t.call(r); }, n: function n() { var r = t.next(); return a = r.done, r; }, e: function e(r) { u = !0, o = r; }, f: function f() { try { a || null == t["return"] || t["return"](); } finally { if (u) throw o; } } }; }
function _unsupportedIterableToArray(r, a) { if (r) { if ("string" == typeof r) return _arrayLikeToArray(r, a); var t = {}.toString.call(r).slice(8, -1); return "Object" === t && r.constructor && (t = r.constructor.name), "Map" === t || "Set" === t ? Array.from(r) : "Arguments" === t || /^(?:Ui|I)nt(?:8|16|32)(?:Clamped)?Array$/.test(t) ? _arrayLikeToArray(r, a) : void 0; } }
function _arrayLikeToArray(r, a) { (null == a || a > r.length) && (a = r.length); for (var e = 0, n = Array(a); e < a; e++) n[e] = r[e]; return n; }
function _classCallCheck(a, n) { if (!(a instanceof n)) throw new TypeError("Cannot call a class as a function"); }
function _defineProperties(e, r) { for (var t = 0; t < r.length; t++) { var o = r[t]; o.enumerable = o.enumerable || !1, o.configurable = !0, "value" in o && (o.writable = !0), Object.defineProperty(e, _toPropertyKey(o.key), o); } }
function _createClass(e, r, t) { return r && _defineProperties(e.prototype, r), t && _defineProperties(e, t), Object.defineProperty(e, "prototype", { writable: !1 }), e; }
function _toPropertyKey(t) { var i = _toPrimitive(t, "string"); return "symbol" == _typeof(i) ? i : i + ""; }
function _toPrimitive(t, r) { if ("object" != _typeof(t) || !t) return t; var e = t[Symbol.toPrimitive]; if (void 0 !== e) { var i = e.call(t, r || "default"); if ("object" != _typeof(i)) return i; throw new TypeError("@@toPrimitive must return a primitive value."); } return ("string" === r ? String : Number)(t); }


var BrowserTools = /*#__PURE__*/function () {
  function BrowserTools() {
    _classCallCheck(this, BrowserTools);
  }
  return _createClass(BrowserTools, [{
    key: "TabHasUrl",
    value:
    /**
     * 
     * @param {*} tab: chrome.tabs.Tab
     * @param {*} targetUrl : string
     * @returns  boolean
     */
    function TabHasUrl(tab, targetUrl) {
      var tabUrl = tab.url ? tab.url : '';
      return _StringTools__WEBPACK_IMPORTED_MODULE_0__["default"].AreEqual(targetUrl, tabUrl, true);
    }

    /**
     * 
     * @param {*} tabs : chrome.tabs.Tab[]
     * @param {*} targetUrl : string
     * @returns 
     */
  }, {
    key: "GetTabsWithUrl",
    value: function GetTabsWithUrl(tabs, targetUrl) {
      var matchedTabs = [];
      var _iterator = _createForOfIteratorHelper(tabs),
        _step;
      try {
        for (_iterator.s(); !(_step = _iterator.n()).done;) {
          var tab = _step.value;
          if (this.TabHasUrl(tab, targetUrl)) matchedTabs.push(tab);
        }
      } catch (err) {
        _iterator.e(err);
      } finally {
        _iterator.f();
      }
      return matchedTabs;
    }
  }, {
    key: "GetPlatform",
    value: function GetPlatform() {
      var platform = "win32";
      var appVersion = navigator.appVersion.toLowerCase();
      if (appVersion.indexOf("mac") != -1) platform = "darwin";else if (appVersion.indexOf("linux") != -1) platform = "linux";
      return platform;
    }
  }, {
    key: "GetChromiumVersion",
    value: function GetChromiumVersion() {
      var raw = navigator.userAgent.match(/Chrom(e|ium)\/([0-9]+)\./);
      return raw ? parseInt(raw[2], 10) : 0;
    }
  }, {
    key: "ForAllSequential",
    value: function ForAllSequential(values, processValueCb, onCompletedAllCb) {
      var valueIndex = 0;
      var doNextAction = function doNextAction() {
        if (valueIndex >= values.length) {
          if (onCompletedAllCb) {
            onCompletedAllCb();
          }
          return;
        }
        processValueCb(values[valueIndex++], function () {
          doNextAction();
        });
      };
      doNextAction();
    }
  }, {
    key: "ValidatePermissions",
    value: function () {
      var _ValidatePermissions = _asyncToGenerator( /*#__PURE__*/_regeneratorRuntime().mark(function _callee() {
        var _chrome$cookies, _chrome$webNavigation, _chrome$downloads, _navigator, _chrome$scripting;
        var cookieStores, _iterator2, _step2, store, tabs, frameDetails, downloadItems, text, _tabs, checkCmplFunc, conn;
        return _regeneratorRuntime().wrap(function _callee$(_context) {
          while (1) switch (_context.prev = _context.next) {
            case 0:
              if (!((_chrome$cookies = chrome.cookies) !== null && _chrome$cookies !== void 0 && _chrome$cookies.getAllCookieStores)) {
                _context.next = 6;
                break;
              }
              _context.next = 3;
              return chrome.cookies.getAllCookieStores();
            case 3:
              cookieStores = _context.sent;
              _iterator2 = _createForOfIteratorHelper(cookieStores);
              try {
                for (_iterator2.s(); !(_step2 = _iterator2.n()).done;) {
                  store = _step2.value;
                  _Logger__WEBPACK_IMPORTED_MODULE_1__["default"].Info("Cookie Store Id: " + cookieStores[i].id);
                }
              } catch (err) {
                _iterator2.e(err);
              } finally {
                _iterator2.f();
              }
            case 6:
              if (!((_chrome$webNavigation = chrome.webNavigation) !== null && _chrome$webNavigation !== void 0 && _chrome$webNavigation.getAllFrames)) {
                _context.next = 15;
                break;
              }
              _context.next = 9;
              return chrome.tabs.query({
                active: true
              });
            case 9:
              tabs = _context.sent;
              if (!(tabs.length != 0)) {
                _context.next = 15;
                break;
              }
              _context.next = 13;
              return chrome.webNavigation.getAllFrames({
                tabId: tabs[0].id || 0
              });
            case 13:
              frameDetails = _context.sent;
              if (frameDetails && frameDetails.length != 0) {
                _Logger__WEBPACK_IMPORTED_MODULE_1__["default"].Info("Active Tab Frame URL: " + frameDetails[0].url);
              }
            case 15:
              if (!((_chrome$downloads = chrome.downloads) !== null && _chrome$downloads !== void 0 && _chrome$downloads.search)) {
                _context.next = 20;
                break;
              }
              _context.next = 18;
              return chrome.downloads.search({
                url: "https://www.winrobot360.com/"
              });
            case 18:
              downloadItems = _context.sent;
              if (downloadItems.length != 0) {
                _Logger__WEBPACK_IMPORTED_MODULE_1__["default"].Info("download item url:", downloadItems[0].url);
              }
            case 20:
              if (!((_navigator = navigator) !== null && _navigator !== void 0 && _navigator.clipboard)) {
                _context.next = 27;
                break;
              }
              _context.next = 23;
              return navigator.clipboard.writeText('https://www.winrobot360.com/');
            case 23:
              _context.next = 25;
              return navigator.clipboard.readText();
            case 25:
              text = _context.sent;
              _Logger__WEBPACK_IMPORTED_MODULE_1__["default"].Info("clipboard text:", text);
            case 27:
              if (!((_chrome$scripting = chrome.scripting) !== null && _chrome$scripting !== void 0 && _chrome$scripting.executeScript)) {
                _context.next = 35;
                break;
              }
              _context.next = 30;
              return chrome.tabs.query({
                active: true
              });
            case 30:
              _tabs = _context.sent;
              if (!(_tabs.length != 0)) {
                _context.next = 35;
                break;
              }
              checkCmplFunc = function checkCmplFunc() {
                return document.readyState === "complete";
              };
              _context.next = 35;
              return chrome.scripting.executeScript({
                target: {
                  allFrames: true,
                  tabId: _tabs[0].id || 0
                },
                func: checkCmplFunc,
                args: []
              });
            case 35:
              conn = chrome.runtime.connectNative("shadowbot.chrome.bridge");
              conn.onMessage.addListener(function (message) {
                if (message) {
                  _Logger__WEBPACK_IMPORTED_MODULE_1__["default"].Info("onNativeMsg:", message);
                } else {
                  _Logger__WEBPACK_IMPORTED_MODULE_1__["default"].Error("unknown msg formst: ".concat(message));
                }
              });
            case 37:
            case "end":
              return _context.stop();
          }
        }, _callee);
      }));
      function ValidatePermissions() {
        return _ValidatePermissions.apply(this, arguments);
      }
      return ValidatePermissions;
    }()
  }]);
}();
var browserTools = new BrowserTools();
/* harmony default export */ __webpack_exports__["default"] = (browserTools);

/***/ }),
/* 4 */
/*!*********************************!*\
  !*** ./Src/Tool/StringTools.js ***!
  \*********************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
function _typeof(o) { "@babel/helpers - typeof"; return _typeof = "function" == typeof Symbol && "symbol" == typeof Symbol.iterator ? function (o) { return typeof o; } : function (o) { return o && "function" == typeof Symbol && o.constructor === Symbol && o !== Symbol.prototype ? "symbol" : typeof o; }, _typeof(o); }
function _classCallCheck(a, n) { if (!(a instanceof n)) throw new TypeError("Cannot call a class as a function"); }
function _defineProperties(e, r) { for (var t = 0; t < r.length; t++) { var o = r[t]; o.enumerable = o.enumerable || !1, o.configurable = !0, "value" in o && (o.writable = !0), Object.defineProperty(e, _toPropertyKey(o.key), o); } }
function _createClass(e, r, t) { return r && _defineProperties(e.prototype, r), t && _defineProperties(e, t), Object.defineProperty(e, "prototype", { writable: !1 }), e; }
function _toPropertyKey(t) { var i = _toPrimitive(t, "string"); return "symbol" == _typeof(i) ? i : i + ""; }
function _toPrimitive(t, r) { if ("object" != _typeof(t) || !t) return t; var e = t[Symbol.toPrimitive]; if (void 0 !== e) { var i = e.call(t, r || "default"); if ("object" != _typeof(i)) return i; throw new TypeError("@@toPrimitive must return a primitive value."); } return ("string" === r ? String : Number)(t); }
var StringTools = /*#__PURE__*/function () {
  function StringTools() {
    _classCallCheck(this, StringTools);
  }
  return _createClass(StringTools, [{
    key: "AreEqual",
    value:
    /**
     * 
     * @param {*} valueA : string
     * @param {*} valueB : string
     * @param {*} ignoreCase : boolean
     * @returns boolean
     */
    function AreEqual(valueA, valueB, ignoreCase) {
      if (valueA === valueB) {
        return true;
      } else if (!valueA || !valueB) {
        return false;
      }
      if (ignoreCase) {
        valueA = valueA.toLowerCase();
        valueB = valueB.toLowerCase();
      }
      return valueA === valueB;
    }

    /**
     * 
     * @param {*} str : string
     * @param {*} valueToReplace : string
     * @param {*} replacement : strings
     * @returns string
     */
  }, {
    key: "SafeReplaceString",
    value: function SafeReplaceString(str, valueToReplace, replacement) {
      var startIndex = str.indexOf(valueToReplace);
      var beginStr = str.slice(0, startIndex);
      var endStr = str.slice(startIndex + valueToReplace.length);
      var result = beginStr;
      result += replacement;
      result += endStr;
      return result;
    }

    /**
     * 
     * @param {*} func : Function
     * @returns string
     */
  }, {
    key: "GetFunctionBody",
    value: function GetFunctionBody(func) {
      var functionCode = func.toString();
      var openBracketIndex = functionCode.indexOf("{");
      var closeBracketIndex = functionCode.lastIndexOf("}");
      var functionBody = functionCode.substring(openBracketIndex + 1, closeBracketIndex);
      return functionBody;
    }
  }]);
}();
var stringTools = new StringTools();
/* harmony default export */ __webpack_exports__["default"] = (stringTools);

/***/ }),
/* 5 */
/*!*******************************!*\
  !*** ./Src/LoaderPortable.js ***!
  \*******************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "default", function() { return LoaderPortable; });
/* harmony import */ var _Service_GlobalVariable__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! ./Service/GlobalVariable */ 6);
/* harmony import */ var _Service_EvalService__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(/*! ./Service/EvalService */ 7);
/* harmony import */ var _Tool_Logger__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(/*! ./Tool/Logger */ 1);
/* harmony import */ var _Service_NativeHost__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(/*! ./Service/NativeHost */ 9);
/* harmony import */ var _Tool_ReturnCallbackMap__WEBPACK_IMPORTED_MODULE_4__ = __webpack_require__(/*! ./Tool/ReturnCallbackMap */ 10);
/* harmony import */ var _Handler_Factory__WEBPACK_IMPORTED_MODULE_5__ = __webpack_require__(/*! ./Handler/Factory */ 11);
function _typeof(o) { "@babel/helpers - typeof"; return _typeof = "function" == typeof Symbol && "symbol" == typeof Symbol.iterator ? function (o) { return typeof o; } : function (o) { return o && "function" == typeof Symbol && o.constructor === Symbol && o !== Symbol.prototype ? "symbol" : typeof o; }, _typeof(o); }
function _regeneratorRuntime() { "use strict"; /*! regenerator-runtime -- Copyright (c) 2014-present, Facebook, Inc. -- license (MIT): https://github.com/facebook/regenerator/blob/main/LICENSE */ _regeneratorRuntime = function _regeneratorRuntime() { return e; }; var t, e = {}, r = Object.prototype, n = r.hasOwnProperty, o = Object.defineProperty || function (t, e, r) { t[e] = r.value; }, i = "function" == typeof Symbol ? Symbol : {}, a = i.iterator || "@@iterator", c = i.asyncIterator || "@@asyncIterator", u = i.toStringTag || "@@toStringTag"; function define(t, e, r) { return Object.defineProperty(t, e, { value: r, enumerable: !0, configurable: !0, writable: !0 }), t[e]; } try { define({}, ""); } catch (t) { define = function define(t, e, r) { return t[e] = r; }; } function wrap(t, e, r, n) { var i = e && e.prototype instanceof Generator ? e : Generator, a = Object.create(i.prototype), c = new Context(n || []); return o(a, "_invoke", { value: makeInvokeMethod(t, r, c) }), a; } function tryCatch(t, e, r) { try { return { type: "normal", arg: t.call(e, r) }; } catch (t) { return { type: "throw", arg: t }; } } e.wrap = wrap; var h = "suspendedStart", l = "suspendedYield", f = "executing", s = "completed", y = {}; function Generator() {} function GeneratorFunction() {} function GeneratorFunctionPrototype() {} var p = {}; define(p, a, function () { return this; }); var d = Object.getPrototypeOf, v = d && d(d(values([]))); v && v !== r && n.call(v, a) && (p = v); var g = GeneratorFunctionPrototype.prototype = Generator.prototype = Object.create(p); function defineIteratorMethods(t) { ["next", "throw", "return"].forEach(function (e) { define(t, e, function (t) { return this._invoke(e, t); }); }); } function AsyncIterator(t, e) { function invoke(r, o, i, a) { var c = tryCatch(t[r], t, o); if ("throw" !== c.type) { var u = c.arg, h = u.value; return h && "object" == _typeof(h) && n.call(h, "__await") ? e.resolve(h.__await).then(function (t) { invoke("next", t, i, a); }, function (t) { invoke("throw", t, i, a); }) : e.resolve(h).then(function (t) { u.value = t, i(u); }, function (t) { return invoke("throw", t, i, a); }); } a(c.arg); } var r; o(this, "_invoke", { value: function value(t, n) { function callInvokeWithMethodAndArg() { return new e(function (e, r) { invoke(t, n, e, r); }); } return r = r ? r.then(callInvokeWithMethodAndArg, callInvokeWithMethodAndArg) : callInvokeWithMethodAndArg(); } }); } function makeInvokeMethod(e, r, n) { var o = h; return function (i, a) { if (o === f) throw Error("Generator is already running"); if (o === s) { if ("throw" === i) throw a; return { value: t, done: !0 }; } for (n.method = i, n.arg = a;;) { var c = n.delegate; if (c) { var u = maybeInvokeDelegate(c, n); if (u) { if (u === y) continue; return u; } } if ("next" === n.method) n.sent = n._sent = n.arg;else if ("throw" === n.method) { if (o === h) throw o = s, n.arg; n.dispatchException(n.arg); } else "return" === n.method && n.abrupt("return", n.arg); o = f; var p = tryCatch(e, r, n); if ("normal" === p.type) { if (o = n.done ? s : l, p.arg === y) continue; return { value: p.arg, done: n.done }; } "throw" === p.type && (o = s, n.method = "throw", n.arg = p.arg); } }; } function maybeInvokeDelegate(e, r) { var n = r.method, o = e.iterator[n]; if (o === t) return r.delegate = null, "throw" === n && e.iterator["return"] && (r.method = "return", r.arg = t, maybeInvokeDelegate(e, r), "throw" === r.method) || "return" !== n && (r.method = "throw", r.arg = new TypeError("The iterator does not provide a '" + n + "' method")), y; var i = tryCatch(o, e.iterator, r.arg); if ("throw" === i.type) return r.method = "throw", r.arg = i.arg, r.delegate = null, y; var a = i.arg; return a ? a.done ? (r[e.resultName] = a.value, r.next = e.nextLoc, "return" !== r.method && (r.method = "next", r.arg = t), r.delegate = null, y) : a : (r.method = "throw", r.arg = new TypeError("iterator result is not an object"), r.delegate = null, y); } function pushTryEntry(t) { var e = { tryLoc: t[0] }; 1 in t && (e.catchLoc = t[1]), 2 in t && (e.finallyLoc = t[2], e.afterLoc = t[3]), this.tryEntries.push(e); } function resetTryEntry(t) { var e = t.completion || {}; e.type = "normal", delete e.arg, t.completion = e; } function Context(t) { this.tryEntries = [{ tryLoc: "root" }], t.forEach(pushTryEntry, this), this.reset(!0); } function values(e) { if (e || "" === e) { var r = e[a]; if (r) return r.call(e); if ("function" == typeof e.next) return e; if (!isNaN(e.length)) { var o = -1, i = function next() { for (; ++o < e.length;) if (n.call(e, o)) return next.value = e[o], next.done = !1, next; return next.value = t, next.done = !0, next; }; return i.next = i; } } throw new TypeError(_typeof(e) + " is not iterable"); } return GeneratorFunction.prototype = GeneratorFunctionPrototype, o(g, "constructor", { value: GeneratorFunctionPrototype, configurable: !0 }), o(GeneratorFunctionPrototype, "constructor", { value: GeneratorFunction, configurable: !0 }), GeneratorFunction.displayName = define(GeneratorFunctionPrototype, u, "GeneratorFunction"), e.isGeneratorFunction = function (t) { var e = "function" == typeof t && t.constructor; return !!e && (e === GeneratorFunction || "GeneratorFunction" === (e.displayName || e.name)); }, e.mark = function (t) { return Object.setPrototypeOf ? Object.setPrototypeOf(t, GeneratorFunctionPrototype) : (t.__proto__ = GeneratorFunctionPrototype, define(t, u, "GeneratorFunction")), t.prototype = Object.create(g), t; }, e.awrap = function (t) { return { __await: t }; }, defineIteratorMethods(AsyncIterator.prototype), define(AsyncIterator.prototype, c, function () { return this; }), e.AsyncIterator = AsyncIterator, e.async = function (t, r, n, o, i) { void 0 === i && (i = Promise); var a = new AsyncIterator(wrap(t, r, n, o), i); return e.isGeneratorFunction(r) ? a : a.next().then(function (t) { return t.done ? t.value : a.next(); }); }, defineIteratorMethods(g), define(g, u, "Generator"), define(g, a, function () { return this; }), define(g, "toString", function () { return "[object Generator]"; }), e.keys = function (t) { var e = Object(t), r = []; for (var n in e) r.push(n); return r.reverse(), function next() { for (; r.length;) { var t = r.pop(); if (t in e) return next.value = t, next.done = !1, next; } return next.done = !0, next; }; }, e.values = values, Context.prototype = { constructor: Context, reset: function reset(e) { if (this.prev = 0, this.next = 0, this.sent = this._sent = t, this.done = !1, this.delegate = null, this.method = "next", this.arg = t, this.tryEntries.forEach(resetTryEntry), !e) for (var r in this) "t" === r.charAt(0) && n.call(this, r) && !isNaN(+r.slice(1)) && (this[r] = t); }, stop: function stop() { this.done = !0; var t = this.tryEntries[0].completion; if ("throw" === t.type) throw t.arg; return this.rval; }, dispatchException: function dispatchException(e) { if (this.done) throw e; var r = this; function handle(n, o) { return a.type = "throw", a.arg = e, r.next = n, o && (r.method = "next", r.arg = t), !!o; } for (var o = this.tryEntries.length - 1; o >= 0; --o) { var i = this.tryEntries[o], a = i.completion; if ("root" === i.tryLoc) return handle("end"); if (i.tryLoc <= this.prev) { var c = n.call(i, "catchLoc"), u = n.call(i, "finallyLoc"); if (c && u) { if (this.prev < i.catchLoc) return handle(i.catchLoc, !0); if (this.prev < i.finallyLoc) return handle(i.finallyLoc); } else if (c) { if (this.prev < i.catchLoc) return handle(i.catchLoc, !0); } else { if (!u) throw Error("try statement without catch or finally"); if (this.prev < i.finallyLoc) return handle(i.finallyLoc); } } } }, abrupt: function abrupt(t, e) { for (var r = this.tryEntries.length - 1; r >= 0; --r) { var o = this.tryEntries[r]; if (o.tryLoc <= this.prev && n.call(o, "finallyLoc") && this.prev < o.finallyLoc) { var i = o; break; } } i && ("break" === t || "continue" === t) && i.tryLoc <= e && e <= i.finallyLoc && (i = null); var a = i ? i.completion : {}; return a.type = t, a.arg = e, i ? (this.method = "next", this.next = i.finallyLoc, y) : this.complete(a); }, complete: function complete(t, e) { if ("throw" === t.type) throw t.arg; return "break" === t.type || "continue" === t.type ? this.next = t.arg : "return" === t.type ? (this.rval = this.arg = t.arg, this.method = "return", this.next = "end") : "normal" === t.type && e && (this.next = e), y; }, finish: function finish(t) { for (var e = this.tryEntries.length - 1; e >= 0; --e) { var r = this.tryEntries[e]; if (r.finallyLoc === t) return this.complete(r.completion, r.afterLoc), resetTryEntry(r), y; } }, "catch": function _catch(t) { for (var e = this.tryEntries.length - 1; e >= 0; --e) { var r = this.tryEntries[e]; if (r.tryLoc === t) { var n = r.completion; if ("throw" === n.type) { var o = n.arg; resetTryEntry(r); } return o; } } throw Error("illegal catch attempt"); }, delegateYield: function delegateYield(e, r, n) { return this.delegate = { iterator: values(e), resultName: r, nextLoc: n }, "next" === this.method && (this.arg = t), y; } }, e; }
function asyncGeneratorStep(n, t, e, r, o, a, c) { try { var i = n[a](c), u = i.value; } catch (n) { return void e(n); } i.done ? t(u) : Promise.resolve(u).then(r, o); }
function _asyncToGenerator(n) { return function () { var t = this, e = arguments; return new Promise(function (r, o) { var a = n.apply(t, e); function _next(n) { asyncGeneratorStep(a, r, o, _next, _throw, "next", n); } function _throw(n) { asyncGeneratorStep(a, r, o, _next, _throw, "throw", n); } _next(void 0); }); }; }
function _classCallCheck(a, n) { if (!(a instanceof n)) throw new TypeError("Cannot call a class as a function"); }
function _defineProperties(e, r) { for (var t = 0; t < r.length; t++) { var o = r[t]; o.enumerable = o.enumerable || !1, o.configurable = !0, "value" in o && (o.writable = !0), Object.defineProperty(e, _toPropertyKey(o.key), o); } }
function _createClass(e, r, t) { return r && _defineProperties(e.prototype, r), t && _defineProperties(e, t), Object.defineProperty(e, "prototype", { writable: !1 }), e; }
function _toPropertyKey(t) { var i = _toPrimitive(t, "string"); return "symbol" == _typeof(i) ? i : i + ""; }
function _toPrimitive(t, r) { if ("object" != _typeof(t) || !t) return t; var e = t[Symbol.toPrimitive]; if (void 0 !== e) { var i = e.call(t, r || "default"); if ("object" != _typeof(i)) return i; throw new TypeError("@@toPrimitive must return a primitive value."); } return ("string" === r ? String : Number)(t); }






var LoaderPortable = /*#__PURE__*/function () {
  function LoaderPortable(inServiceWorker) {
    _classCallCheck(this, LoaderPortable);
    _Service_GlobalVariable__WEBPACK_IMPORTED_MODULE_0__["default"].RegisterAll(inServiceWorker);

    //#region 共享的变量
    this.inServiceWorker = inServiceWorker;
    this.nativeHost = new _Service_NativeHost__WEBPACK_IMPORTED_MODULE_3__["default"]();
    this.extensionWndId = 0;
    this.extensionTabId = 0;
    this.evalService = null;
    //#endregion

    // 消息处理器
    this.msgHandler = null;

    // 按需缓存第一条uia消息
    this.canHandleUiaMsg = false;
    this.firstUiaMsg = null;

    // 回调类消息
    this.callbackMap = new _Tool_ReturnCallbackMap__WEBPACK_IMPORTED_MODULE_4__["default"]();
  }
  return _createClass(LoaderPortable, [{
    key: "Init",
    value: function () {
      var _Init = _asyncToGenerator( /*#__PURE__*/_regeneratorRuntime().mark(function _callee() {
        var _this = this;
        var _extWnd$id, extWnd, tabs, extensionTab;
        return _regeneratorRuntime().wrap(function _callee$(_context) {
          while (1) switch (_context.prev = _context.next) {
            case 0:
              _Tool_Logger__WEBPACK_IMPORTED_MODULE_2__["default"].Info("[LoaderPortable::Init] connect nativeHost start");
              _context.next = 3;
              return this.nativeHost.Start(function (message) {
                // provider在连接上nativeHost后，会无脑发送消息，因此必须第一时间注册消息处理器
                _this.DispatchMessage(message);
              });
            case 3:
              _Tool_Logger__WEBPACK_IMPORTED_MODULE_2__["default"].Info("[LoaderPortable::Init] connect nativeHost finish");
              _Tool_Logger__WEBPACK_IMPORTED_MODULE_2__["default"].Info("[LoaderPortable::Init] bridgeInterfaceVersion: ".concat(this.nativeHost.GetBridgeInterfaceVersion()));
              if (!this.inServiceWorker) {
                _context.next = 10;
                break;
              }
              this.evalService = new _Service_EvalService__WEBPACK_IMPORTED_MODULE_1__["default"](null);
              _Service_GlobalVariable__WEBPACK_IMPORTED_MODULE_0__["default"].RegisterEvalService(this.evalService);
              _context.next = 22;
              break;
            case 10:
              _context.next = 12;
              return chrome.windows.getCurrent();
            case 12:
              extWnd = _context.sent;
              this.extensionWndId = (_extWnd$id = extWnd.id) !== null && _extWnd$id !== void 0 ? _extWnd$id : 0;
              _Tool_Logger__WEBPACK_IMPORTED_MODULE_2__["default"].Info("[LoaderPortable::Init] extensionWndId: ".concat(this.extensionWndId));
              _context.next = 17;
              return chrome.tabs.query({
                currentWindow: true
              });
            case 17:
              tabs = _context.sent;
              extensionTab = tabs.find(function (tab) {
                return tab.url === chrome.runtime.getURL('BackgroundPage.html');
              });
              if (extensionTab) {
                this.extensionTabId = extensionTab.id;
                _Tool_Logger__WEBPACK_IMPORTED_MODULE_2__["default"].Info("[LoaderPortable::Init] extensionTabId: ".concat(this.extensionTabId));
              } else {
                _Tool_Logger__WEBPACK_IMPORTED_MODULE_2__["default"].Error("[LoaderPortable::Init] failed to get extensionTabId");
              }
              this.evalService = new _Service_EvalService__WEBPACK_IMPORTED_MODULE_1__["default"](this.extensionTabId);
              _Service_GlobalVariable__WEBPACK_IMPORTED_MODULE_0__["default"].RegisterEvalService(this.evalService);
            case 22:
              _Tool_Logger__WEBPACK_IMPORTED_MODULE_2__["default"].Info("[LoaderPortable::Init] register windowHandler");
              this.msgHandler = Object(_Handler_Factory__WEBPACK_IMPORTED_MODULE_5__["CreateWindowHandler"])(this);
              _Tool_Logger__WEBPACK_IMPORTED_MODULE_2__["default"].Info("[LoaderPortable::Init] windowHandler init start");
              _context.next = 27;
              return this.msgHandler.Init();
            case 27:
              _Tool_Logger__WEBPACK_IMPORTED_MODULE_2__["default"].Info("[LoaderPortable::Init] windowHandler init finish");
              this.EnableUiaMsgHandle();
            case 29:
            case "end":
              return _context.stop();
          }
        }, _callee, this);
      }));
      function Init() {
        return _Init.apply(this, arguments);
      }
      return Init;
    }()
  }, {
    key: "EnableUiaMsgHandle",
    value: function EnableUiaMsgHandle() {
      _Tool_Logger__WEBPACK_IMPORTED_MODULE_2__["default"].Info("[LoaderPortable::EnableUiaMsgHandle]");
      this.canHandleUiaMsg = true;
      if (this.firstUiaMsg) {
        var msg = this.firstUiaMsg;
        this.firstUiaMsg = null;
        _Tool_Logger__WEBPACK_IMPORTED_MODULE_2__["default"].Info("[LoaderPortable::EnableUiaMsgHandle] triggerFirstUiaMsg: ".concat(JSON.stringify(msg)));
        this.DispatchMessage(msg);
      }
    }
  }, {
    key: "IsUiaMessage",
    value: function IsUiaMessage(message) {
      if (typeof message.method === 'string' && message.method !== 'Window.SetHwnd' && !message.method.startsWith("Bridge.")) return true;
      return false;
    }
  }, {
    key: "DispatchMessage",
    value: function DispatchMessage(message) {
      var _this2 = this;
      _Tool_Logger__WEBPACK_IMPORTED_MODULE_2__["default"].Debug("[LoaderPortable::DispatchMessage] ".concat(JSON.stringify(message)));
      if (!message) {
        _Tool_Logger__WEBPACK_IMPORTED_MODULE_2__["default"].Error("[LoaderPortable::DispatchMessage] unknown msg format: ".concat(message));
        return;
      }

      // uia 消息在 windowHandler.Init() 结束前到来了，此时需要缓存它
      if (!this.canHandleUiaMsg && this.IsUiaMessage(message)) {
        this.firstUiaMsg = message;
        _Tool_Logger__WEBPACK_IMPORTED_MODULE_2__["default"].Info("[LoaderPortable::DispatchMessage] recordFirstUiaMsg: ".concat(JSON.stringify(this.firstUiaMsg)));
        return;
      }

      // this.msgHandler = windowHandler 之前的消息无需处理（如：Bridge.GetInterfaceVersion）
      if (!this.msgHandler) {
        _Tool_Logger__WEBPACK_IMPORTED_MODULE_2__["default"].Debug("[LoaderPortable::DispatchMessage] ignore message: ".concat(JSON.stringify(message)));
        return;
      }

      // 消息处理流程
      if (message.requestId != null) {
        this.callbackMap.HandleReturnCallback(message.requestId, message.params);
        return;
      }
      if (this.msgHandler.canHandleMessage(message)) {
        this.msgHandler.handleMessage(message);
      } else {
        if (window.uiaDispatcher) {
          uiaDispatcher.invoke(message, function (response) {
            _this2.nativeHost.PostMessage(response);
          });
        } else {
          _Tool_Logger__WEBPACK_IMPORTED_MODULE_2__["default"].Error("[LoaderPortable::DispatchMessage] uiaDispatcher not initialized");
          this.nativeHost.Response({
            content: null,
            error: {
              code: -1,
              message: 'uiaDispatcher not initialized'
            }
          });
        }
      }
    }
  }, {
    key: "CallNativeHostFunction",
    value: function CallNativeHostFunction(method, params, returnFunc) {
      if (returnFunc) {
        var requestId = this.callbackMap.RegisterReturnCallback(returnFunc);
        this.nativeHost.PostMessage({
          requestId: requestId,
          method: method,
          params: params
        });
      } else {
        this.nativeHost.PostMessage({
          method: method,
          params: params
        });
      }
    }
  }]);
}();


/***/ }),
/* 6 */
/*!***************************************!*\
  !*** ./Src/Service/GlobalVariable.js ***!
  \***************************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* harmony import */ var _Tool_Logger__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! ../Tool/Logger */ 1);
function _typeof(o) { "@babel/helpers - typeof"; return _typeof = "function" == typeof Symbol && "symbol" == typeof Symbol.iterator ? function (o) { return typeof o; } : function (o) { return o && "function" == typeof Symbol && o.constructor === Symbol && o !== Symbol.prototype ? "symbol" : typeof o; }, _typeof(o); }
function _classCallCheck(a, n) { if (!(a instanceof n)) throw new TypeError("Cannot call a class as a function"); }
function _defineProperties(e, r) { for (var t = 0; t < r.length; t++) { var o = r[t]; o.enumerable = o.enumerable || !1, o.configurable = !0, "value" in o && (o.writable = !0), Object.defineProperty(e, _toPropertyKey(o.key), o); } }
function _createClass(e, r, t) { return r && _defineProperties(e.prototype, r), t && _defineProperties(e, t), Object.defineProperty(e, "prototype", { writable: !1 }), e; }
function _toPropertyKey(t) { var i = _toPrimitive(t, "string"); return "symbol" == _typeof(i) ? i : i + ""; }
function _toPrimitive(t, r) { if ("object" != _typeof(t) || !t) return t; var e = t[Symbol.toPrimitive]; if (void 0 !== e) { var i = e.call(t, r || "default"); if ("object" != _typeof(i)) return i; throw new TypeError("@@toPrimitive must return a primitive value."); } return ("string" === r ? String : Number)(t); }


/**
 * 能够被 background_dynamic.js 直接使用的变量称之为全局变量，否则不应该放在这里
 */
var GlobalVariable = /*#__PURE__*/function () {
  function GlobalVariable() {
    _classCallCheck(this, GlobalVariable);
  }
  return _createClass(GlobalVariable, null, [{
    key: "RegisterAll",
    value: function RegisterAll(inServiceWorker) {
      if (inServiceWorker) {
        globalThis.window = globalThis;
      }
      window.wnd2HwndDict = {};
      window.xbotDriver = {
        version: '1.0.1',
        evalService: null,
        // start from 1.0.0
        logger: _Tool_Logger__WEBPACK_IMPORTED_MODULE_0__["default"],
        // start from 1.0.0
        inServiceWorker: inServiceWorker // start from 1.0.1
      };
    }
  }, {
    key: "RegisterEvalService",
    value: function RegisterEvalService(evalService) {
      _Tool_Logger__WEBPACK_IMPORTED_MODULE_0__["default"].Info("[GlobalVariable::RegisterEvalService]");
      window.xbotDriver.evalService = evalService;
    }
  }]);
}();
/* harmony default export */ __webpack_exports__["default"] = (GlobalVariable);

/***/ }),
/* 7 */
/*!************************************!*\
  !*** ./Src/Service/EvalService.js ***!
  \************************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* harmony import */ var _Tool_ChromeWrapper__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! ../Tool/ChromeWrapper */ 8);
/* harmony import */ var _Tool_Logger__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(/*! ../Tool/Logger */ 1);
/* harmony import */ var _Tool_StringTools__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(/*! ../Tool/StringTools */ 4);
function _typeof(o) { "@babel/helpers - typeof"; return _typeof = "function" == typeof Symbol && "symbol" == typeof Symbol.iterator ? function (o) { return typeof o; } : function (o) { return o && "function" == typeof Symbol && o.constructor === Symbol && o !== Symbol.prototype ? "symbol" : typeof o; }, _typeof(o); }
function _createForOfIteratorHelper(r, e) { var t = "undefined" != typeof Symbol && r[Symbol.iterator] || r["@@iterator"]; if (!t) { if (Array.isArray(r) || (t = _unsupportedIterableToArray(r)) || e && r && "number" == typeof r.length) { t && (r = t); var _n = 0, F = function F() {}; return { s: F, n: function n() { return _n >= r.length ? { done: !0 } : { done: !1, value: r[_n++] }; }, e: function e(r) { throw r; }, f: F }; } throw new TypeError("Invalid attempt to iterate non-iterable instance.\nIn order to be iterable, non-array objects must have a [Symbol.iterator]() method."); } var o, a = !0, u = !1; return { s: function s() { t = t.call(r); }, n: function n() { var r = t.next(); return a = r.done, r; }, e: function e(r) { u = !0, o = r; }, f: function f() { try { a || null == t["return"] || t["return"](); } finally { if (u) throw o; } } }; }
function _unsupportedIterableToArray(r, a) { if (r) { if ("string" == typeof r) return _arrayLikeToArray(r, a); var t = {}.toString.call(r).slice(8, -1); return "Object" === t && r.constructor && (t = r.constructor.name), "Map" === t || "Set" === t ? Array.from(r) : "Arguments" === t || /^(?:Ui|I)nt(?:8|16|32)(?:Clamped)?Array$/.test(t) ? _arrayLikeToArray(r, a) : void 0; } }
function _arrayLikeToArray(r, a) { (null == a || a > r.length) && (a = r.length); for (var e = 0, n = Array(a); e < a; e++) n[e] = r[e]; return n; }
function _regeneratorRuntime() { "use strict"; /*! regenerator-runtime -- Copyright (c) 2014-present, Facebook, Inc. -- license (MIT): https://github.com/facebook/regenerator/blob/main/LICENSE */ _regeneratorRuntime = function _regeneratorRuntime() { return e; }; var t, e = {}, r = Object.prototype, n = r.hasOwnProperty, o = Object.defineProperty || function (t, e, r) { t[e] = r.value; }, i = "function" == typeof Symbol ? Symbol : {}, a = i.iterator || "@@iterator", c = i.asyncIterator || "@@asyncIterator", u = i.toStringTag || "@@toStringTag"; function define(t, e, r) { return Object.defineProperty(t, e, { value: r, enumerable: !0, configurable: !0, writable: !0 }), t[e]; } try { define({}, ""); } catch (t) { define = function define(t, e, r) { return t[e] = r; }; } function wrap(t, e, r, n) { var i = e && e.prototype instanceof Generator ? e : Generator, a = Object.create(i.prototype), c = new Context(n || []); return o(a, "_invoke", { value: makeInvokeMethod(t, r, c) }), a; } function tryCatch(t, e, r) { try { return { type: "normal", arg: t.call(e, r) }; } catch (t) { return { type: "throw", arg: t }; } } e.wrap = wrap; var h = "suspendedStart", l = "suspendedYield", f = "executing", s = "completed", y = {}; function Generator() {} function GeneratorFunction() {} function GeneratorFunctionPrototype() {} var p = {}; define(p, a, function () { return this; }); var d = Object.getPrototypeOf, v = d && d(d(values([]))); v && v !== r && n.call(v, a) && (p = v); var g = GeneratorFunctionPrototype.prototype = Generator.prototype = Object.create(p); function defineIteratorMethods(t) { ["next", "throw", "return"].forEach(function (e) { define(t, e, function (t) { return this._invoke(e, t); }); }); } function AsyncIterator(t, e) { function invoke(r, o, i, a) { var c = tryCatch(t[r], t, o); if ("throw" !== c.type) { var u = c.arg, h = u.value; return h && "object" == _typeof(h) && n.call(h, "__await") ? e.resolve(h.__await).then(function (t) { invoke("next", t, i, a); }, function (t) { invoke("throw", t, i, a); }) : e.resolve(h).then(function (t) { u.value = t, i(u); }, function (t) { return invoke("throw", t, i, a); }); } a(c.arg); } var r; o(this, "_invoke", { value: function value(t, n) { function callInvokeWithMethodAndArg() { return new e(function (e, r) { invoke(t, n, e, r); }); } return r = r ? r.then(callInvokeWithMethodAndArg, callInvokeWithMethodAndArg) : callInvokeWithMethodAndArg(); } }); } function makeInvokeMethod(e, r, n) { var o = h; return function (i, a) { if (o === f) throw Error("Generator is already running"); if (o === s) { if ("throw" === i) throw a; return { value: t, done: !0 }; } for (n.method = i, n.arg = a;;) { var c = n.delegate; if (c) { var u = maybeInvokeDelegate(c, n); if (u) { if (u === y) continue; return u; } } if ("next" === n.method) n.sent = n._sent = n.arg;else if ("throw" === n.method) { if (o === h) throw o = s, n.arg; n.dispatchException(n.arg); } else "return" === n.method && n.abrupt("return", n.arg); o = f; var p = tryCatch(e, r, n); if ("normal" === p.type) { if (o = n.done ? s : l, p.arg === y) continue; return { value: p.arg, done: n.done }; } "throw" === p.type && (o = s, n.method = "throw", n.arg = p.arg); } }; } function maybeInvokeDelegate(e, r) { var n = r.method, o = e.iterator[n]; if (o === t) return r.delegate = null, "throw" === n && e.iterator["return"] && (r.method = "return", r.arg = t, maybeInvokeDelegate(e, r), "throw" === r.method) || "return" !== n && (r.method = "throw", r.arg = new TypeError("The iterator does not provide a '" + n + "' method")), y; var i = tryCatch(o, e.iterator, r.arg); if ("throw" === i.type) return r.method = "throw", r.arg = i.arg, r.delegate = null, y; var a = i.arg; return a ? a.done ? (r[e.resultName] = a.value, r.next = e.nextLoc, "return" !== r.method && (r.method = "next", r.arg = t), r.delegate = null, y) : a : (r.method = "throw", r.arg = new TypeError("iterator result is not an object"), r.delegate = null, y); } function pushTryEntry(t) { var e = { tryLoc: t[0] }; 1 in t && (e.catchLoc = t[1]), 2 in t && (e.finallyLoc = t[2], e.afterLoc = t[3]), this.tryEntries.push(e); } function resetTryEntry(t) { var e = t.completion || {}; e.type = "normal", delete e.arg, t.completion = e; } function Context(t) { this.tryEntries = [{ tryLoc: "root" }], t.forEach(pushTryEntry, this), this.reset(!0); } function values(e) { if (e || "" === e) { var r = e[a]; if (r) return r.call(e); if ("function" == typeof e.next) return e; if (!isNaN(e.length)) { var o = -1, i = function next() { for (; ++o < e.length;) if (n.call(e, o)) return next.value = e[o], next.done = !1, next; return next.value = t, next.done = !0, next; }; return i.next = i; } } throw new TypeError(_typeof(e) + " is not iterable"); } return GeneratorFunction.prototype = GeneratorFunctionPrototype, o(g, "constructor", { value: GeneratorFunctionPrototype, configurable: !0 }), o(GeneratorFunctionPrototype, "constructor", { value: GeneratorFunction, configurable: !0 }), GeneratorFunction.displayName = define(GeneratorFunctionPrototype, u, "GeneratorFunction"), e.isGeneratorFunction = function (t) { var e = "function" == typeof t && t.constructor; return !!e && (e === GeneratorFunction || "GeneratorFunction" === (e.displayName || e.name)); }, e.mark = function (t) { return Object.setPrototypeOf ? Object.setPrototypeOf(t, GeneratorFunctionPrototype) : (t.__proto__ = GeneratorFunctionPrototype, define(t, u, "GeneratorFunction")), t.prototype = Object.create(g), t; }, e.awrap = function (t) { return { __await: t }; }, defineIteratorMethods(AsyncIterator.prototype), define(AsyncIterator.prototype, c, function () { return this; }), e.AsyncIterator = AsyncIterator, e.async = function (t, r, n, o, i) { void 0 === i && (i = Promise); var a = new AsyncIterator(wrap(t, r, n, o), i); return e.isGeneratorFunction(r) ? a : a.next().then(function (t) { return t.done ? t.value : a.next(); }); }, defineIteratorMethods(g), define(g, u, "Generator"), define(g, a, function () { return this; }), define(g, "toString", function () { return "[object Generator]"; }), e.keys = function (t) { var e = Object(t), r = []; for (var n in e) r.push(n); return r.reverse(), function next() { for (; r.length;) { var t = r.pop(); if (t in e) return next.value = t, next.done = !1, next; } return next.done = !0, next; }; }, e.values = values, Context.prototype = { constructor: Context, reset: function reset(e) { if (this.prev = 0, this.next = 0, this.sent = this._sent = t, this.done = !1, this.delegate = null, this.method = "next", this.arg = t, this.tryEntries.forEach(resetTryEntry), !e) for (var r in this) "t" === r.charAt(0) && n.call(this, r) && !isNaN(+r.slice(1)) && (this[r] = t); }, stop: function stop() { this.done = !0; var t = this.tryEntries[0].completion; if ("throw" === t.type) throw t.arg; return this.rval; }, dispatchException: function dispatchException(e) { if (this.done) throw e; var r = this; function handle(n, o) { return a.type = "throw", a.arg = e, r.next = n, o && (r.method = "next", r.arg = t), !!o; } for (var o = this.tryEntries.length - 1; o >= 0; --o) { var i = this.tryEntries[o], a = i.completion; if ("root" === i.tryLoc) return handle("end"); if (i.tryLoc <= this.prev) { var c = n.call(i, "catchLoc"), u = n.call(i, "finallyLoc"); if (c && u) { if (this.prev < i.catchLoc) return handle(i.catchLoc, !0); if (this.prev < i.finallyLoc) return handle(i.finallyLoc); } else if (c) { if (this.prev < i.catchLoc) return handle(i.catchLoc, !0); } else { if (!u) throw Error("try statement without catch or finally"); if (this.prev < i.finallyLoc) return handle(i.finallyLoc); } } } }, abrupt: function abrupt(t, e) { for (var r = this.tryEntries.length - 1; r >= 0; --r) { var o = this.tryEntries[r]; if (o.tryLoc <= this.prev && n.call(o, "finallyLoc") && this.prev < o.finallyLoc) { var i = o; break; } } i && ("break" === t || "continue" === t) && i.tryLoc <= e && e <= i.finallyLoc && (i = null); var a = i ? i.completion : {}; return a.type = t, a.arg = e, i ? (this.method = "next", this.next = i.finallyLoc, y) : this.complete(a); }, complete: function complete(t, e) { if ("throw" === t.type) throw t.arg; return "break" === t.type || "continue" === t.type ? this.next = t.arg : "return" === t.type ? (this.rval = this.arg = t.arg, this.method = "return", this.next = "end") : "normal" === t.type && e && (this.next = e), y; }, finish: function finish(t) { for (var e = this.tryEntries.length - 1; e >= 0; --e) { var r = this.tryEntries[e]; if (r.finallyLoc === t) return this.complete(r.completion, r.afterLoc), resetTryEntry(r), y; } }, "catch": function _catch(t) { for (var e = this.tryEntries.length - 1; e >= 0; --e) { var r = this.tryEntries[e]; if (r.tryLoc === t) { var n = r.completion; if ("throw" === n.type) { var o = n.arg; resetTryEntry(r); } return o; } } throw Error("illegal catch attempt"); }, delegateYield: function delegateYield(e, r, n) { return this.delegate = { iterator: values(e), resultName: r, nextLoc: n }, "next" === this.method && (this.arg = t), y; } }, e; }
function asyncGeneratorStep(n, t, e, r, o, a, c) { try { var i = n[a](c), u = i.value; } catch (n) { return void e(n); } i.done ? t(u) : Promise.resolve(u).then(r, o); }
function _asyncToGenerator(n) { return function () { var t = this, e = arguments; return new Promise(function (r, o) { var a = n.apply(t, e); function _next(n) { asyncGeneratorStep(a, r, o, _next, _throw, "next", n); } function _throw(n) { asyncGeneratorStep(a, r, o, _next, _throw, "throw", n); } _next(void 0); }); }; }
function _classCallCheck(a, n) { if (!(a instanceof n)) throw new TypeError("Cannot call a class as a function"); }
function _defineProperties(e, r) { for (var t = 0; t < r.length; t++) { var o = r[t]; o.enumerable = o.enumerable || !1, o.configurable = !0, "value" in o && (o.writable = !0), Object.defineProperty(e, _toPropertyKey(o.key), o); } }
function _createClass(e, r, t) { return r && _defineProperties(e.prototype, r), t && _defineProperties(e, t), Object.defineProperty(e, "prototype", { writable: !1 }), e; }
function _toPropertyKey(t) { var i = _toPrimitive(t, "string"); return "symbol" == _typeof(i) ? i : i + ""; }
function _toPrimitive(t, r) { if ("object" != _typeof(t) || !t) return t; var e = t[Symbol.toPrimitive]; if (void 0 !== e) { var i = e.call(t, r || "default"); if ("object" != _typeof(i)) return i; throw new TypeError("@@toPrimitive must return a primitive value."); } return ("string" === r ? String : Number)(t); }



var DebuggerEvalService = /*#__PURE__*/function () {
  /**
   * @param {*} extensionTabId: number | null, number：附加到指定背景页, null: 附加到service_worker
   */
  function DebuggerEvalService(extensionTabId) {
    var _this = this;
    _classCallCheck(this, DebuggerEvalService);
    this.extensionTabId = extensionTabId;
    this.debuggerVersion = "1.2";
    this.backgroundPageDebugTarget = null;
    this.evalFuncId = 0;
    this.isEvalRestricted = true;
    this.savedFuncsDic = {};
    this.savedFuncsByCodeDic = {};
    chrome["debugger"].onDetach.addListener(function (source, reason) {
      _this.OnDebuggerDetached(source, reason);
    });
  }
  return _createClass(DebuggerEvalService, [{
    key: "Clear",
    value: function Clear() {
      this.savedFuncsDic = {};
    }
  }, {
    key: "EvalCodeInBackgroundPage",
    value: function EvalCodeInBackgroundPage(code, onFinishedCb) {
      this.EvalCodeInBackgroundPage_Async(code).then(onFinishedCb);
    }

    /**
     * start from xbotDriver 1.0.0
     * 因为历史原因带了_Async后缀，后续新接口不再带_Async后缀
     * @param {*} code 
     * @param {*} savedFuncName 
     * @returns 
     */
  }, {
    key: "EvalFunctionInBackgroundPage_Async",
    value: (function () {
      var _EvalFunctionInBackgroundPage_Async = _asyncToGenerator( /*#__PURE__*/_regeneratorRuntime().mark(function _callee(code) {
        var savedFuncName,
          evalFuncName,
          evalCodeWrapper,
          evalResult,
          evalFunc,
          _args = arguments;
        return _regeneratorRuntime().wrap(function _callee$(_context) {
          while (1) switch (_context.prev = _context.next) {
            case 0:
              savedFuncName = _args.length > 1 && _args[1] !== undefined ? _args[1] : '';
              if (!(savedFuncName && this.savedFuncsDic[savedFuncName])) {
                _context.next = 5;
                break;
              }
              return _context.abrupt("return", {
                success: true,
                evalFunc: this.savedFuncsDic[savedFuncName]
              });
            case 5:
              if (!this.savedFuncsByCodeDic[code]) {
                _context.next = 7;
                break;
              }
              return _context.abrupt("return", {
                success: true,
                evalFunc: this.savedFuncsByCodeDic[code]
              });
            case 7:
              evalFuncName = this.GetNextEvalFuncName();
              evalCodeWrapper = this.GetDebuggerEvalWrapperCode(evalFuncName, code);
              _context.next = 11;
              return this.EvalCodeInBackgroundPage_Async(evalCodeWrapper);
            case 11:
              evalResult = _context.sent;
              if (evalResult.success) {
                _context.next = 14;
                break;
              }
              return _context.abrupt("return", evalResult);
            case 14:
              evalFunc = this.GetDebuggerEvalWrapperFunc(evalFuncName);
              if (evalFunc) {
                _context.next = 17;
                break;
              }
              return _context.abrupt("return", {
                success: false,
                errorMsg: "Failed to load code"
              });
            case 17:
              if (savedFuncName) this.savedFuncsDic[savedFuncName] = evalFunc;else {
                // 针对影刀5.17以下版本内存泄漏问题进行的优化，主要是优化过大的content code
                // 大量小的code无法优化，通过字典保存，相当于产生了两倍的内存占用，这类代码5.17已经进行了优化
                if (code.length > 1024) this.savedFuncsByCodeDic[code] = evalFunc;
              }
              return _context.abrupt("return", {
                success: true,
                evalFunc: evalFunc
              });
            case 19:
            case "end":
              return _context.stop();
          }
        }, _callee, this);
      }));
      function EvalFunctionInBackgroundPage_Async(_x) {
        return _EvalFunctionInBackgroundPage_Async.apply(this, arguments);
      }
      return EvalFunctionInBackgroundPage_Async;
    }()
    /**
     * start from xbotDriver 1.0.0
     * 因为历史原因带了_Async后缀，后续新代码中不再带_Async后缀
     * @param {*} code 
     * @returns 
     */
    )
  }, {
    key: "EvalCodeInBackgroundPage_Async",
    value: (function () {
      var _EvalCodeInBackgroundPage_Async = _asyncToGenerator( /*#__PURE__*/_regeneratorRuntime().mark(function _callee2(code) {
        var debugTarget;
        return _regeneratorRuntime().wrap(function _callee2$(_context2) {
          while (1) switch (_context2.prev = _context2.next) {
            case 0:
              _context2.next = 2;
              return this.AttachToBackgroundPage();
            case 2:
              debugTarget = _context2.sent;
              if (debugTarget) {
                _context2.next = 5;
                break;
              }
              return _context2.abrupt("return", {
                success: false,
                errorMsg: "Failed to attach debugger to background page"
              });
            case 5:
              return _context2.abrupt("return", this.SendEvalCommand(debugTarget, code));
            case 6:
            case "end":
              return _context2.stop();
          }
        }, _callee2, this);
      }));
      function EvalCodeInBackgroundPage_Async(_x2) {
        return _EvalCodeInBackgroundPage_Async.apply(this, arguments);
      }
      return EvalCodeInBackgroundPage_Async;
    }())
  }, {
    key: "AttachToBackgroundPage",
    value: function () {
      var _AttachToBackgroundPage = _asyncToGenerator( /*#__PURE__*/_regeneratorRuntime().mark(function _callee3() {
        var targetId, previousTarget, target, isAttached;
        return _regeneratorRuntime().wrap(function _callee3$(_context3) {
          while (1) switch (_context3.prev = _context3.next) {
            case 0:
              _context3.next = 2;
              return this.FindDebugTargetId();
            case 2:
              targetId = _context3.sent;
              if (!(targetId == null)) {
                _context3.next = 5;
                break;
              }
              return _context3.abrupt("return", null);
            case 5:
              if (!(this.backgroundPageDebugTarget != null && this.backgroundPageDebugTarget.targetId == targetId)) {
                _context3.next = 8;
                break;
              }
              _Tool_Logger__WEBPACK_IMPORTED_MODULE_1__["default"].Info("[DebuggerEvalService::AttachToBackgroundPage] use cached target: ".concat(targetId));
              return _context3.abrupt("return", this.backgroundPageDebugTarget);
            case 8:
              previousTarget = this.ClearBackgroundPageDebugTarget();
              if (!previousTarget) {
                _context3.next = 13;
                break;
              }
              _Tool_Logger__WEBPACK_IMPORTED_MODULE_1__["default"].Info("[DebuggerEvalService::AttachToBackgroundPage] Dettaching debugger from previous background page:", previousTarget.targetId);
              _context3.next = 13;
              return this.DettachDebugger(previousTarget);
            case 13:
              target = {
                targetId: targetId
              };
              _context3.next = 16;
              return this.AttachDebugger(target);
            case 16:
              isAttached = _context3.sent;
              if (isAttached) {
                _context3.next = 19;
                break;
              }
              return _context3.abrupt("return", null);
            case 19:
              this.SetBackgroundPageDebugTarget(target);
              return _context3.abrupt("return", target);
            case 21:
            case "end":
              return _context3.stop();
          }
        }, _callee3, this);
      }));
      function AttachToBackgroundPage() {
        return _AttachToBackgroundPage.apply(this, arguments);
      }
      return AttachToBackgroundPage;
    }()
  }, {
    key: "SendEvalCommand",
    value: function () {
      var _SendEvalCommand = _asyncToGenerator( /*#__PURE__*/_regeneratorRuntime().mark(function _callee4(debugTarget, codeToEval) {
        return _regeneratorRuntime().wrap(function _callee4$(_context4) {
          while (1) switch (_context4.prev = _context4.next) {
            case 0:
              return _context4.abrupt("return", new Promise(function (res) {
                var methodName = "Runtime.evaluate";
                var commandParams = {
                  expression: codeToEval
                };
                chrome["debugger"].sendCommand(debugTarget, methodName, commandParams, function (resultObj) {
                  var errorMsg = null;
                  if (chrome.runtime.lastError) {
                    errorMsg = chrome.runtime.lastError.message || '';
                  } else if (resultObj == undefined || resultObj.exceptionDetails != undefined) {
                    var _resultObj$exceptionD;
                    errorMsg = (resultObj == undefined ? "unknown eval error" : (_resultObj$exceptionD = resultObj.exceptionDetails) === null || _resultObj$exceptionD === void 0 || (_resultObj$exceptionD = _resultObj$exceptionD.exception) === null || _resultObj$exceptionD === void 0 ? void 0 : _resultObj$exceptionD.description) || '';
                  }
                  if (errorMsg != null) {
                    _Tool_Logger__WEBPACK_IMPORTED_MODULE_1__["default"].Error('[DebuggerEvalService::SendEvalCommand] Failed to evaluate code. ErrorMsg is ', errorMsg);
                  } else {
                    _Tool_Logger__WEBPACK_IMPORTED_MODULE_1__["default"].Info('[DebuggerEvalService::SendEvalCommand] success');
                  }
                  var result = errorMsg != null ? {
                    success: false,
                    errorMsg: errorMsg
                  } : {
                    success: true
                  };
                  return res(result);
                });
              }));
            case 1:
            case "end":
              return _context4.stop();
          }
        }, _callee4);
      }));
      function SendEvalCommand(_x3, _x4) {
        return _SendEvalCommand.apply(this, arguments);
      }
      return SendEvalCommand;
    }()
    /**
     * 
     * @returns Promise<null | number>
     */
  }, {
    key: "FindDebugTargetId",
    value: (function () {
      var _FindDebugTargetId = _asyncToGenerator( /*#__PURE__*/_regeneratorRuntime().mark(function _callee5() {
        var targetUrl, debugTargets, _iterator, _step, target;
        return _regeneratorRuntime().wrap(function _callee5$(_context5) {
          while (1) switch (_context5.prev = _context5.next) {
            case 0:
              targetUrl = chrome.runtime.getURL("BackgroundPage.html");
              if (this.extensionTabId == null) {
                targetUrl = chrome.runtime.getURL("BackgroundServiceWorker.js");
              }
              _context5.next = 4;
              return _Tool_ChromeWrapper__WEBPACK_IMPORTED_MODULE_0__["default"].Debugger_GetTargets();
            case 4:
              debugTargets = _context5.sent;
              _iterator = _createForOfIteratorHelper(debugTargets);
              _context5.prev = 6;
              _iterator.s();
            case 8:
              if ((_step = _iterator.n()).done) {
                _context5.next = 17;
                break;
              }
              target = _step.value;
              if (!(target.url === targetUrl)) {
                _context5.next = 15;
                break;
              }
              if (!(this.extensionTabId == null)) {
                _context5.next = 13;
                break;
              }
              return _context5.abrupt("return", target.id);
            case 13:
              if (!(target.tabId == this.extensionTabId)) {
                _context5.next = 15;
                break;
              }
              return _context5.abrupt("return", target.id);
            case 15:
              _context5.next = 8;
              break;
            case 17:
              _context5.next = 22;
              break;
            case 19:
              _context5.prev = 19;
              _context5.t0 = _context5["catch"](6);
              _iterator.e(_context5.t0);
            case 22:
              _context5.prev = 22;
              _iterator.f();
              return _context5.finish(22);
            case 25:
              _Tool_Logger__WEBPACK_IMPORTED_MODULE_1__["default"].Error("[DebuggerEvalService::FindDebugTargetId] could not find debugTargetId for targetUrl: ".concat(targetUrl, " targetTabId: ").concat(this.extensionTabId, ". targets is "), debugTargets);
              return _context5.abrupt("return", null);
            case 27:
            case "end":
              return _context5.stop();
          }
        }, _callee5, this, [[6, 19, 22, 25]]);
      }));
      function FindDebugTargetId() {
        return _FindDebugTargetId.apply(this, arguments);
      }
      return FindDebugTargetId;
    }())
  }, {
    key: "AttachDebugger",
    value: function () {
      var _AttachDebugger = _asyncToGenerator( /*#__PURE__*/_regeneratorRuntime().mark(function _callee7(target) {
        var _this2 = this;
        return _regeneratorRuntime().wrap(function _callee7$(_context7) {
          while (1) switch (_context7.prev = _context7.next) {
            case 0:
              return _context7.abrupt("return", new Promise(function (res) {
                chrome["debugger"].attach(target, _this2.debuggerVersion, /*#__PURE__*/_asyncToGenerator( /*#__PURE__*/_regeneratorRuntime().mark(function _callee6() {
                  var errorMsg, isAttached;
                  return _regeneratorRuntime().wrap(function _callee6$(_context6) {
                    while (1) switch (_context6.prev = _context6.next) {
                      case 0:
                        if (!chrome.runtime.lastError) {
                          _context6.next = 9;
                          break;
                        }
                        errorMsg = chrome.runtime.lastError.message || "attach debugger failed";
                        _context6.next = 4;
                        return _this2.IsDebuggerAttached(target);
                      case 4:
                        isAttached = _context6.sent;
                        if (isAttached) {
                          _Tool_Logger__WEBPACK_IMPORTED_MODULE_1__["default"].Warn("[DebuggerEvalService::AttachDebugger] debugger is already attached to target. ErrorMsg is ", errorMsg);
                        } else {
                          _Tool_Logger__WEBPACK_IMPORTED_MODULE_1__["default"].Error("[DebuggerEvalService::AttachDebugger] Failed to attach debugger to target ".concat(target.targetId, ". ErrorMsg is "), errorMsg);
                        }
                        return _context6.abrupt("return", res(isAttached));
                      case 9:
                        _Tool_Logger__WEBPACK_IMPORTED_MODULE_1__["default"].Info("[DebuggerEvalService::AttachDebugger] debugger attached");
                        return _context6.abrupt("return", res(true));
                      case 11:
                      case "end":
                        return _context6.stop();
                    }
                  }, _callee6);
                })));
              }));
            case 1:
            case "end":
              return _context7.stop();
          }
        }, _callee7);
      }));
      function AttachDebugger(_x5) {
        return _AttachDebugger.apply(this, arguments);
      }
      return AttachDebugger;
    }()
  }, {
    key: "DettachDebugger",
    value: function () {
      var _DettachDebugger = _asyncToGenerator( /*#__PURE__*/_regeneratorRuntime().mark(function _callee8(target) {
        return _regeneratorRuntime().wrap(function _callee8$(_context8) {
          while (1) switch (_context8.prev = _context8.next) {
            case 0:
              _context8.next = 2;
              return _Tool_ChromeWrapper__WEBPACK_IMPORTED_MODULE_0__["default"].Debugger_Detach(target);
            case 2:
            case "end":
              return _context8.stop();
          }
        }, _callee8);
      }));
      function DettachDebugger(_x6) {
        return _DettachDebugger.apply(this, arguments);
      }
      return DettachDebugger;
    }()
  }, {
    key: "IsDebuggerAttached",
    value: function () {
      var _IsDebuggerAttached = _asyncToGenerator( /*#__PURE__*/_regeneratorRuntime().mark(function _callee9(targetToCheck) {
        var debugTargets, _iterator2, _step2, target;
        return _regeneratorRuntime().wrap(function _callee9$(_context9) {
          while (1) switch (_context9.prev = _context9.next) {
            case 0:
              _context9.next = 2;
              return _Tool_ChromeWrapper__WEBPACK_IMPORTED_MODULE_0__["default"].Debugger_GetTargets();
            case 2:
              debugTargets = _context9.sent;
              _iterator2 = _createForOfIteratorHelper(debugTargets);
              _context9.prev = 4;
              _iterator2.s();
            case 6:
              if ((_step2 = _iterator2.n()).done) {
                _context9.next = 12;
                break;
              }
              target = _step2.value;
              if (!(target.id == targetToCheck.targetId)) {
                _context9.next = 10;
                break;
              }
              return _context9.abrupt("return", target.attached);
            case 10:
              _context9.next = 6;
              break;
            case 12:
              _context9.next = 17;
              break;
            case 14:
              _context9.prev = 14;
              _context9.t0 = _context9["catch"](4);
              _iterator2.e(_context9.t0);
            case 17:
              _context9.prev = 17;
              _iterator2.f();
              return _context9.finish(17);
            case 20:
              return _context9.abrupt("return", false);
            case 21:
            case "end":
              return _context9.stop();
          }
        }, _callee9, null, [[4, 14, 17, 20]]);
      }));
      function IsDebuggerAttached(_x7) {
        return _IsDebuggerAttached.apply(this, arguments);
      }
      return IsDebuggerAttached;
    }()
  }, {
    key: "OnDebuggerDetached",
    value: function OnDebuggerDetached(source, reason) {
      if (this.backgroundPageDebugTarget != null && this.backgroundPageDebugTarget.targetId === source.targetId) {
        _Tool_Logger__WEBPACK_IMPORTED_MODULE_1__["default"].Info("[DebuggerEvalService::OnDebuggerDetached] Debugger detached from background page. reason:", reason);
        this.ClearBackgroundPageDebugTarget();
      }
    }
  }, {
    key: "SetBackgroundPageDebugTarget",
    value: function SetBackgroundPageDebugTarget(source) {
      this.backgroundPageDebugTarget = source;
    }
  }, {
    key: "ClearBackgroundPageDebugTarget",
    value: function ClearBackgroundPageDebugTarget() {
      var previousTarget = this.backgroundPageDebugTarget;
      this.backgroundPageDebugTarget = null;
      return previousTarget;
    }
  }, {
    key: "GetNextEvalFuncName",
    value: function GetNextEvalFuncName() {
      if (this.evalFuncId >= Number.MAX_SAFE_INTEGER) {
        this.evalFuncId = 0;
      }
      this.evalFuncId = this.evalFuncId + 1;
      var funcName = "ExtensionDebuggerEvalFunc_" + this.evalFuncId;
      return funcName;
    }
  }, {
    key: "GetDebuggerEvalWrapperCode",
    value: function GetDebuggerEvalWrapperCode(evalFuncName, codeToEval) {
      var functionTemplate = function functionTemplate() {
        window["evalFuncName"] = function () {
          codeToEval;
        };
      };
      var template = _Tool_StringTools__WEBPACK_IMPORTED_MODULE_2__["default"].GetFunctionBody(functionTemplate);
      var evalWrapper = _Tool_StringTools__WEBPACK_IMPORTED_MODULE_2__["default"].SafeReplaceString(template, "evalFuncName", evalFuncName);
      evalWrapper = _Tool_StringTools__WEBPACK_IMPORTED_MODULE_2__["default"].SafeReplaceString(evalWrapper, "codeToEval", codeToEval);
      return evalWrapper;
    }
  }, {
    key: "GetDebuggerEvalWrapperFunc",
    value: function GetDebuggerEvalWrapperFunc(evalFuncName) {
      var wrapperFunc = window[evalFuncName];
      if (wrapperFunc) {
        delete window[evalFuncName];
      } else {
        _Tool_Logger__WEBPACK_IMPORTED_MODULE_1__["default"].Error("[DebuggerEvalService::GetDebuggerEvalWrapperFunc] Could not find window.evalFuncName: ".concat(evalFuncName));
      }
      return wrapperFunc;
    }
  }]);
}();
/* harmony default export */ __webpack_exports__["default"] = (DebuggerEvalService);

/***/ }),
/* 8 */
/*!***********************************!*\
  !*** ./Src/Tool/ChromeWrapper.js ***!
  \***********************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
function _typeof(o) { "@babel/helpers - typeof"; return _typeof = "function" == typeof Symbol && "symbol" == typeof Symbol.iterator ? function (o) { return typeof o; } : function (o) { return o && "function" == typeof Symbol && o.constructor === Symbol && o !== Symbol.prototype ? "symbol" : typeof o; }, _typeof(o); }
function _regeneratorRuntime() { "use strict"; /*! regenerator-runtime -- Copyright (c) 2014-present, Facebook, Inc. -- license (MIT): https://github.com/facebook/regenerator/blob/main/LICENSE */ _regeneratorRuntime = function _regeneratorRuntime() { return e; }; var t, e = {}, r = Object.prototype, n = r.hasOwnProperty, o = Object.defineProperty || function (t, e, r) { t[e] = r.value; }, i = "function" == typeof Symbol ? Symbol : {}, a = i.iterator || "@@iterator", c = i.asyncIterator || "@@asyncIterator", u = i.toStringTag || "@@toStringTag"; function define(t, e, r) { return Object.defineProperty(t, e, { value: r, enumerable: !0, configurable: !0, writable: !0 }), t[e]; } try { define({}, ""); } catch (t) { define = function define(t, e, r) { return t[e] = r; }; } function wrap(t, e, r, n) { var i = e && e.prototype instanceof Generator ? e : Generator, a = Object.create(i.prototype), c = new Context(n || []); return o(a, "_invoke", { value: makeInvokeMethod(t, r, c) }), a; } function tryCatch(t, e, r) { try { return { type: "normal", arg: t.call(e, r) }; } catch (t) { return { type: "throw", arg: t }; } } e.wrap = wrap; var h = "suspendedStart", l = "suspendedYield", f = "executing", s = "completed", y = {}; function Generator() {} function GeneratorFunction() {} function GeneratorFunctionPrototype() {} var p = {}; define(p, a, function () { return this; }); var d = Object.getPrototypeOf, v = d && d(d(values([]))); v && v !== r && n.call(v, a) && (p = v); var g = GeneratorFunctionPrototype.prototype = Generator.prototype = Object.create(p); function defineIteratorMethods(t) { ["next", "throw", "return"].forEach(function (e) { define(t, e, function (t) { return this._invoke(e, t); }); }); } function AsyncIterator(t, e) { function invoke(r, o, i, a) { var c = tryCatch(t[r], t, o); if ("throw" !== c.type) { var u = c.arg, h = u.value; return h && "object" == _typeof(h) && n.call(h, "__await") ? e.resolve(h.__await).then(function (t) { invoke("next", t, i, a); }, function (t) { invoke("throw", t, i, a); }) : e.resolve(h).then(function (t) { u.value = t, i(u); }, function (t) { return invoke("throw", t, i, a); }); } a(c.arg); } var r; o(this, "_invoke", { value: function value(t, n) { function callInvokeWithMethodAndArg() { return new e(function (e, r) { invoke(t, n, e, r); }); } return r = r ? r.then(callInvokeWithMethodAndArg, callInvokeWithMethodAndArg) : callInvokeWithMethodAndArg(); } }); } function makeInvokeMethod(e, r, n) { var o = h; return function (i, a) { if (o === f) throw Error("Generator is already running"); if (o === s) { if ("throw" === i) throw a; return { value: t, done: !0 }; } for (n.method = i, n.arg = a;;) { var c = n.delegate; if (c) { var u = maybeInvokeDelegate(c, n); if (u) { if (u === y) continue; return u; } } if ("next" === n.method) n.sent = n._sent = n.arg;else if ("throw" === n.method) { if (o === h) throw o = s, n.arg; n.dispatchException(n.arg); } else "return" === n.method && n.abrupt("return", n.arg); o = f; var p = tryCatch(e, r, n); if ("normal" === p.type) { if (o = n.done ? s : l, p.arg === y) continue; return { value: p.arg, done: n.done }; } "throw" === p.type && (o = s, n.method = "throw", n.arg = p.arg); } }; } function maybeInvokeDelegate(e, r) { var n = r.method, o = e.iterator[n]; if (o === t) return r.delegate = null, "throw" === n && e.iterator["return"] && (r.method = "return", r.arg = t, maybeInvokeDelegate(e, r), "throw" === r.method) || "return" !== n && (r.method = "throw", r.arg = new TypeError("The iterator does not provide a '" + n + "' method")), y; var i = tryCatch(o, e.iterator, r.arg); if ("throw" === i.type) return r.method = "throw", r.arg = i.arg, r.delegate = null, y; var a = i.arg; return a ? a.done ? (r[e.resultName] = a.value, r.next = e.nextLoc, "return" !== r.method && (r.method = "next", r.arg = t), r.delegate = null, y) : a : (r.method = "throw", r.arg = new TypeError("iterator result is not an object"), r.delegate = null, y); } function pushTryEntry(t) { var e = { tryLoc: t[0] }; 1 in t && (e.catchLoc = t[1]), 2 in t && (e.finallyLoc = t[2], e.afterLoc = t[3]), this.tryEntries.push(e); } function resetTryEntry(t) { var e = t.completion || {}; e.type = "normal", delete e.arg, t.completion = e; } function Context(t) { this.tryEntries = [{ tryLoc: "root" }], t.forEach(pushTryEntry, this), this.reset(!0); } function values(e) { if (e || "" === e) { var r = e[a]; if (r) return r.call(e); if ("function" == typeof e.next) return e; if (!isNaN(e.length)) { var o = -1, i = function next() { for (; ++o < e.length;) if (n.call(e, o)) return next.value = e[o], next.done = !1, next; return next.value = t, next.done = !0, next; }; return i.next = i; } } throw new TypeError(_typeof(e) + " is not iterable"); } return GeneratorFunction.prototype = GeneratorFunctionPrototype, o(g, "constructor", { value: GeneratorFunctionPrototype, configurable: !0 }), o(GeneratorFunctionPrototype, "constructor", { value: GeneratorFunction, configurable: !0 }), GeneratorFunction.displayName = define(GeneratorFunctionPrototype, u, "GeneratorFunction"), e.isGeneratorFunction = function (t) { var e = "function" == typeof t && t.constructor; return !!e && (e === GeneratorFunction || "GeneratorFunction" === (e.displayName || e.name)); }, e.mark = function (t) { return Object.setPrototypeOf ? Object.setPrototypeOf(t, GeneratorFunctionPrototype) : (t.__proto__ = GeneratorFunctionPrototype, define(t, u, "GeneratorFunction")), t.prototype = Object.create(g), t; }, e.awrap = function (t) { return { __await: t }; }, defineIteratorMethods(AsyncIterator.prototype), define(AsyncIterator.prototype, c, function () { return this; }), e.AsyncIterator = AsyncIterator, e.async = function (t, r, n, o, i) { void 0 === i && (i = Promise); var a = new AsyncIterator(wrap(t, r, n, o), i); return e.isGeneratorFunction(r) ? a : a.next().then(function (t) { return t.done ? t.value : a.next(); }); }, defineIteratorMethods(g), define(g, u, "Generator"), define(g, a, function () { return this; }), define(g, "toString", function () { return "[object Generator]"; }), e.keys = function (t) { var e = Object(t), r = []; for (var n in e) r.push(n); return r.reverse(), function next() { for (; r.length;) { var t = r.pop(); if (t in e) return next.value = t, next.done = !1, next; } return next.done = !0, next; }; }, e.values = values, Context.prototype = { constructor: Context, reset: function reset(e) { if (this.prev = 0, this.next = 0, this.sent = this._sent = t, this.done = !1, this.delegate = null, this.method = "next", this.arg = t, this.tryEntries.forEach(resetTryEntry), !e) for (var r in this) "t" === r.charAt(0) && n.call(this, r) && !isNaN(+r.slice(1)) && (this[r] = t); }, stop: function stop() { this.done = !0; var t = this.tryEntries[0].completion; if ("throw" === t.type) throw t.arg; return this.rval; }, dispatchException: function dispatchException(e) { if (this.done) throw e; var r = this; function handle(n, o) { return a.type = "throw", a.arg = e, r.next = n, o && (r.method = "next", r.arg = t), !!o; } for (var o = this.tryEntries.length - 1; o >= 0; --o) { var i = this.tryEntries[o], a = i.completion; if ("root" === i.tryLoc) return handle("end"); if (i.tryLoc <= this.prev) { var c = n.call(i, "catchLoc"), u = n.call(i, "finallyLoc"); if (c && u) { if (this.prev < i.catchLoc) return handle(i.catchLoc, !0); if (this.prev < i.finallyLoc) return handle(i.finallyLoc); } else if (c) { if (this.prev < i.catchLoc) return handle(i.catchLoc, !0); } else { if (!u) throw Error("try statement without catch or finally"); if (this.prev < i.finallyLoc) return handle(i.finallyLoc); } } } }, abrupt: function abrupt(t, e) { for (var r = this.tryEntries.length - 1; r >= 0; --r) { var o = this.tryEntries[r]; if (o.tryLoc <= this.prev && n.call(o, "finallyLoc") && this.prev < o.finallyLoc) { var i = o; break; } } i && ("break" === t || "continue" === t) && i.tryLoc <= e && e <= i.finallyLoc && (i = null); var a = i ? i.completion : {}; return a.type = t, a.arg = e, i ? (this.method = "next", this.next = i.finallyLoc, y) : this.complete(a); }, complete: function complete(t, e) { if ("throw" === t.type) throw t.arg; return "break" === t.type || "continue" === t.type ? this.next = t.arg : "return" === t.type ? (this.rval = this.arg = t.arg, this.method = "return", this.next = "end") : "normal" === t.type && e && (this.next = e), y; }, finish: function finish(t) { for (var e = this.tryEntries.length - 1; e >= 0; --e) { var r = this.tryEntries[e]; if (r.finallyLoc === t) return this.complete(r.completion, r.afterLoc), resetTryEntry(r), y; } }, "catch": function _catch(t) { for (var e = this.tryEntries.length - 1; e >= 0; --e) { var r = this.tryEntries[e]; if (r.tryLoc === t) { var n = r.completion; if ("throw" === n.type) { var o = n.arg; resetTryEntry(r); } return o; } } throw Error("illegal catch attempt"); }, delegateYield: function delegateYield(e, r, n) { return this.delegate = { iterator: values(e), resultName: r, nextLoc: n }, "next" === this.method && (this.arg = t), y; } }, e; }
function asyncGeneratorStep(n, t, e, r, o, a, c) { try { var i = n[a](c), u = i.value; } catch (n) { return void e(n); } i.done ? t(u) : Promise.resolve(u).then(r, o); }
function _asyncToGenerator(n) { return function () { var t = this, e = arguments; return new Promise(function (r, o) { var a = n.apply(t, e); function _next(n) { asyncGeneratorStep(a, r, o, _next, _throw, "next", n); } function _throw(n) { asyncGeneratorStep(a, r, o, _next, _throw, "throw", n); } _next(void 0); }); }; }
function _classCallCheck(a, n) { if (!(a instanceof n)) throw new TypeError("Cannot call a class as a function"); }
function _defineProperties(e, r) { for (var t = 0; t < r.length; t++) { var o = r[t]; o.enumerable = o.enumerable || !1, o.configurable = !0, "value" in o && (o.writable = !0), Object.defineProperty(e, _toPropertyKey(o.key), o); } }
function _createClass(e, r, t) { return r && _defineProperties(e.prototype, r), t && _defineProperties(e, t), Object.defineProperty(e, "prototype", { writable: !1 }), e; }
function _toPropertyKey(t) { var i = _toPrimitive(t, "string"); return "symbol" == _typeof(i) ? i : i + ""; }
function _toPrimitive(t, r) { if ("object" != _typeof(t) || !t) return t; var e = t[Symbol.toPrimitive]; if (void 0 !== e) { var i = e.call(t, r || "default"); if ("object" != _typeof(i)) return i; throw new TypeError("@@toPrimitive must return a primitive value."); } return ("string" === r ? String : Number)(t); }
var ChromeWrapper = /*#__PURE__*/function () {
  function ChromeWrapper() {
    _classCallCheck(this, ChromeWrapper);
  }
  return _createClass(ChromeWrapper, [{
    key: "Debugger_GetTargets",
    value: function () {
      var _Debugger_GetTargets = _asyncToGenerator( /*#__PURE__*/_regeneratorRuntime().mark(function _callee() {
        return _regeneratorRuntime().wrap(function _callee$(_context) {
          while (1) switch (_context.prev = _context.next) {
            case 0:
              return _context.abrupt("return", new Promise(function (res) {
                chrome["debugger"].getTargets(function (targetInfos) {
                  return res(targetInfos);
                });
              }));
            case 1:
            case "end":
              return _context.stop();
          }
        }, _callee);
      }));
      function Debugger_GetTargets() {
        return _Debugger_GetTargets.apply(this, arguments);
      }
      return Debugger_GetTargets;
    }()
  }, {
    key: "Debugger_Detach",
    value: function () {
      var _Debugger_Detach = _asyncToGenerator( /*#__PURE__*/_regeneratorRuntime().mark(function _callee2(target) {
        return _regeneratorRuntime().wrap(function _callee2$(_context2) {
          while (1) switch (_context2.prev = _context2.next) {
            case 0:
              return _context2.abrupt("return", new Promise(function (res) {
                chrome["debugger"].detach(target, function () {
                  return res();
                });
              }));
            case 1:
            case "end":
              return _context2.stop();
          }
        }, _callee2);
      }));
      function Debugger_Detach(_x) {
        return _Debugger_Detach.apply(this, arguments);
      }
      return Debugger_Detach;
    }()
  }]);
}();
var chromeWrapper = new ChromeWrapper();
/* harmony default export */ __webpack_exports__["default"] = (chromeWrapper);

/***/ }),
/* 9 */
/*!***********************************!*\
  !*** ./Src/Service/NativeHost.js ***!
  \***********************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "default", function() { return NativeHost; });
/* harmony import */ var _Tool_Logger__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! ../Tool/Logger */ 1);
function _typeof(o) { "@babel/helpers - typeof"; return _typeof = "function" == typeof Symbol && "symbol" == typeof Symbol.iterator ? function (o) { return typeof o; } : function (o) { return o && "function" == typeof Symbol && o.constructor === Symbol && o !== Symbol.prototype ? "symbol" : typeof o; }, _typeof(o); }
function _regeneratorRuntime() { "use strict"; /*! regenerator-runtime -- Copyright (c) 2014-present, Facebook, Inc. -- license (MIT): https://github.com/facebook/regenerator/blob/main/LICENSE */ _regeneratorRuntime = function _regeneratorRuntime() { return e; }; var t, e = {}, r = Object.prototype, n = r.hasOwnProperty, o = Object.defineProperty || function (t, e, r) { t[e] = r.value; }, i = "function" == typeof Symbol ? Symbol : {}, a = i.iterator || "@@iterator", c = i.asyncIterator || "@@asyncIterator", u = i.toStringTag || "@@toStringTag"; function define(t, e, r) { return Object.defineProperty(t, e, { value: r, enumerable: !0, configurable: !0, writable: !0 }), t[e]; } try { define({}, ""); } catch (t) { define = function define(t, e, r) { return t[e] = r; }; } function wrap(t, e, r, n) { var i = e && e.prototype instanceof Generator ? e : Generator, a = Object.create(i.prototype), c = new Context(n || []); return o(a, "_invoke", { value: makeInvokeMethod(t, r, c) }), a; } function tryCatch(t, e, r) { try { return { type: "normal", arg: t.call(e, r) }; } catch (t) { return { type: "throw", arg: t }; } } e.wrap = wrap; var h = "suspendedStart", l = "suspendedYield", f = "executing", s = "completed", y = {}; function Generator() {} function GeneratorFunction() {} function GeneratorFunctionPrototype() {} var p = {}; define(p, a, function () { return this; }); var d = Object.getPrototypeOf, v = d && d(d(values([]))); v && v !== r && n.call(v, a) && (p = v); var g = GeneratorFunctionPrototype.prototype = Generator.prototype = Object.create(p); function defineIteratorMethods(t) { ["next", "throw", "return"].forEach(function (e) { define(t, e, function (t) { return this._invoke(e, t); }); }); } function AsyncIterator(t, e) { function invoke(r, o, i, a) { var c = tryCatch(t[r], t, o); if ("throw" !== c.type) { var u = c.arg, h = u.value; return h && "object" == _typeof(h) && n.call(h, "__await") ? e.resolve(h.__await).then(function (t) { invoke("next", t, i, a); }, function (t) { invoke("throw", t, i, a); }) : e.resolve(h).then(function (t) { u.value = t, i(u); }, function (t) { return invoke("throw", t, i, a); }); } a(c.arg); } var r; o(this, "_invoke", { value: function value(t, n) { function callInvokeWithMethodAndArg() { return new e(function (e, r) { invoke(t, n, e, r); }); } return r = r ? r.then(callInvokeWithMethodAndArg, callInvokeWithMethodAndArg) : callInvokeWithMethodAndArg(); } }); } function makeInvokeMethod(e, r, n) { var o = h; return function (i, a) { if (o === f) throw Error("Generator is already running"); if (o === s) { if ("throw" === i) throw a; return { value: t, done: !0 }; } for (n.method = i, n.arg = a;;) { var c = n.delegate; if (c) { var u = maybeInvokeDelegate(c, n); if (u) { if (u === y) continue; return u; } } if ("next" === n.method) n.sent = n._sent = n.arg;else if ("throw" === n.method) { if (o === h) throw o = s, n.arg; n.dispatchException(n.arg); } else "return" === n.method && n.abrupt("return", n.arg); o = f; var p = tryCatch(e, r, n); if ("normal" === p.type) { if (o = n.done ? s : l, p.arg === y) continue; return { value: p.arg, done: n.done }; } "throw" === p.type && (o = s, n.method = "throw", n.arg = p.arg); } }; } function maybeInvokeDelegate(e, r) { var n = r.method, o = e.iterator[n]; if (o === t) return r.delegate = null, "throw" === n && e.iterator["return"] && (r.method = "return", r.arg = t, maybeInvokeDelegate(e, r), "throw" === r.method) || "return" !== n && (r.method = "throw", r.arg = new TypeError("The iterator does not provide a '" + n + "' method")), y; var i = tryCatch(o, e.iterator, r.arg); if ("throw" === i.type) return r.method = "throw", r.arg = i.arg, r.delegate = null, y; var a = i.arg; return a ? a.done ? (r[e.resultName] = a.value, r.next = e.nextLoc, "return" !== r.method && (r.method = "next", r.arg = t), r.delegate = null, y) : a : (r.method = "throw", r.arg = new TypeError("iterator result is not an object"), r.delegate = null, y); } function pushTryEntry(t) { var e = { tryLoc: t[0] }; 1 in t && (e.catchLoc = t[1]), 2 in t && (e.finallyLoc = t[2], e.afterLoc = t[3]), this.tryEntries.push(e); } function resetTryEntry(t) { var e = t.completion || {}; e.type = "normal", delete e.arg, t.completion = e; } function Context(t) { this.tryEntries = [{ tryLoc: "root" }], t.forEach(pushTryEntry, this), this.reset(!0); } function values(e) { if (e || "" === e) { var r = e[a]; if (r) return r.call(e); if ("function" == typeof e.next) return e; if (!isNaN(e.length)) { var o = -1, i = function next() { for (; ++o < e.length;) if (n.call(e, o)) return next.value = e[o], next.done = !1, next; return next.value = t, next.done = !0, next; }; return i.next = i; } } throw new TypeError(_typeof(e) + " is not iterable"); } return GeneratorFunction.prototype = GeneratorFunctionPrototype, o(g, "constructor", { value: GeneratorFunctionPrototype, configurable: !0 }), o(GeneratorFunctionPrototype, "constructor", { value: GeneratorFunction, configurable: !0 }), GeneratorFunction.displayName = define(GeneratorFunctionPrototype, u, "GeneratorFunction"), e.isGeneratorFunction = function (t) { var e = "function" == typeof t && t.constructor; return !!e && (e === GeneratorFunction || "GeneratorFunction" === (e.displayName || e.name)); }, e.mark = function (t) { return Object.setPrototypeOf ? Object.setPrototypeOf(t, GeneratorFunctionPrototype) : (t.__proto__ = GeneratorFunctionPrototype, define(t, u, "GeneratorFunction")), t.prototype = Object.create(g), t; }, e.awrap = function (t) { return { __await: t }; }, defineIteratorMethods(AsyncIterator.prototype), define(AsyncIterator.prototype, c, function () { return this; }), e.AsyncIterator = AsyncIterator, e.async = function (t, r, n, o, i) { void 0 === i && (i = Promise); var a = new AsyncIterator(wrap(t, r, n, o), i); return e.isGeneratorFunction(r) ? a : a.next().then(function (t) { return t.done ? t.value : a.next(); }); }, defineIteratorMethods(g), define(g, u, "Generator"), define(g, a, function () { return this; }), define(g, "toString", function () { return "[object Generator]"; }), e.keys = function (t) { var e = Object(t), r = []; for (var n in e) r.push(n); return r.reverse(), function next() { for (; r.length;) { var t = r.pop(); if (t in e) return next.value = t, next.done = !1, next; } return next.done = !0, next; }; }, e.values = values, Context.prototype = { constructor: Context, reset: function reset(e) { if (this.prev = 0, this.next = 0, this.sent = this._sent = t, this.done = !1, this.delegate = null, this.method = "next", this.arg = t, this.tryEntries.forEach(resetTryEntry), !e) for (var r in this) "t" === r.charAt(0) && n.call(this, r) && !isNaN(+r.slice(1)) && (this[r] = t); }, stop: function stop() { this.done = !0; var t = this.tryEntries[0].completion; if ("throw" === t.type) throw t.arg; return this.rval; }, dispatchException: function dispatchException(e) { if (this.done) throw e; var r = this; function handle(n, o) { return a.type = "throw", a.arg = e, r.next = n, o && (r.method = "next", r.arg = t), !!o; } for (var o = this.tryEntries.length - 1; o >= 0; --o) { var i = this.tryEntries[o], a = i.completion; if ("root" === i.tryLoc) return handle("end"); if (i.tryLoc <= this.prev) { var c = n.call(i, "catchLoc"), u = n.call(i, "finallyLoc"); if (c && u) { if (this.prev < i.catchLoc) return handle(i.catchLoc, !0); if (this.prev < i.finallyLoc) return handle(i.finallyLoc); } else if (c) { if (this.prev < i.catchLoc) return handle(i.catchLoc, !0); } else { if (!u) throw Error("try statement without catch or finally"); if (this.prev < i.finallyLoc) return handle(i.finallyLoc); } } } }, abrupt: function abrupt(t, e) { for (var r = this.tryEntries.length - 1; r >= 0; --r) { var o = this.tryEntries[r]; if (o.tryLoc <= this.prev && n.call(o, "finallyLoc") && this.prev < o.finallyLoc) { var i = o; break; } } i && ("break" === t || "continue" === t) && i.tryLoc <= e && e <= i.finallyLoc && (i = null); var a = i ? i.completion : {}; return a.type = t, a.arg = e, i ? (this.method = "next", this.next = i.finallyLoc, y) : this.complete(a); }, complete: function complete(t, e) { if ("throw" === t.type) throw t.arg; return "break" === t.type || "continue" === t.type ? this.next = t.arg : "return" === t.type ? (this.rval = this.arg = t.arg, this.method = "return", this.next = "end") : "normal" === t.type && e && (this.next = e), y; }, finish: function finish(t) { for (var e = this.tryEntries.length - 1; e >= 0; --e) { var r = this.tryEntries[e]; if (r.finallyLoc === t) return this.complete(r.completion, r.afterLoc), resetTryEntry(r), y; } }, "catch": function _catch(t) { for (var e = this.tryEntries.length - 1; e >= 0; --e) { var r = this.tryEntries[e]; if (r.tryLoc === t) { var n = r.completion; if ("throw" === n.type) { var o = n.arg; resetTryEntry(r); } return o; } } throw Error("illegal catch attempt"); }, delegateYield: function delegateYield(e, r, n) { return this.delegate = { iterator: values(e), resultName: r, nextLoc: n }, "next" === this.method && (this.arg = t), y; } }, e; }
function asyncGeneratorStep(n, t, e, r, o, a, c) { try { var i = n[a](c), u = i.value; } catch (n) { return void e(n); } i.done ? t(u) : Promise.resolve(u).then(r, o); }
function _asyncToGenerator(n) { return function () { var t = this, e = arguments; return new Promise(function (r, o) { var a = n.apply(t, e); function _next(n) { asyncGeneratorStep(a, r, o, _next, _throw, "next", n); } function _throw(n) { asyncGeneratorStep(a, r, o, _next, _throw, "throw", n); } _next(void 0); }); }; }
function _classCallCheck(a, n) { if (!(a instanceof n)) throw new TypeError("Cannot call a class as a function"); }
function _defineProperties(e, r) { for (var t = 0; t < r.length; t++) { var o = r[t]; o.enumerable = o.enumerable || !1, o.configurable = !0, "value" in o && (o.writable = !0), Object.defineProperty(e, _toPropertyKey(o.key), o); } }
function _createClass(e, r, t) { return r && _defineProperties(e.prototype, r), t && _defineProperties(e, t), Object.defineProperty(e, "prototype", { writable: !1 }), e; }
function _defineProperty(e, r, t) { return (r = _toPropertyKey(r)) in e ? Object.defineProperty(e, r, { value: t, enumerable: !0, configurable: !0, writable: !0 }) : e[r] = t, e; }
function _toPropertyKey(t) { var i = _toPrimitive(t, "string"); return "symbol" == _typeof(i) ? i : i + ""; }
function _toPrimitive(t, r) { if ("object" != _typeof(t) || !t) return t; var e = t[Symbol.toPrimitive]; if (void 0 !== e) { var i = e.call(t, r || "default"); if ("object" != _typeof(i)) return i; throw new TypeError("@@toPrimitive must return a primitive value."); } return ("string" === r ? String : Number)(t); }

var NativeHost = /*#__PURE__*/function () {
  function NativeHost() {
    var _this = this;
    _classCallCheck(this, NativeHost);
    _defineProperty(this, "Response", function (result) {
      if (_this.CheckConnection()) _this.conn.postMessage({
        code: 200,
        status: 'OK',
        result: result
      });
    });
    _defineProperty(this, "PostMessage", function (message) {
      if (_this.CheckConnection()) _this.conn.postMessage(message);
    });
    this.conn = null;
    this.bridgeInterfaceVersion = '1.0';
    this.disconnected = false;
    this.disconnectedReason = '';
  }

  /**
   * 
   * @returns Promise<Port>
   */
  return _createClass(NativeHost, [{
    key: "Start",
    value: (function () {
      var _Start = _asyncToGenerator( /*#__PURE__*/_regeneratorRuntime().mark(function _callee(msgHandler) {
        var _this2 = this;
        var nativeHostKey;
        return _regeneratorRuntime().wrap(function _callee$(_context) {
          while (1) switch (_context.prev = _context.next) {
            case 0:
              _context.next = 2;
              return this._StartNativeHost_v2(msgHandler);
            case 2:
              this.conn = _context.sent;
              if (this.conn == null) {
                _Tool_Logger__WEBPACK_IMPORTED_MODULE_0__["default"].Info("[NativeHost::start] startNativeHost_v2 failed, fallback to v1");
                nativeHostKey = 'shadowbot.chrome.bridge';
                this.conn = chrome.runtime.connectNative(nativeHostKey);
                this.conn.onMessage.addListener(msgHandler);
                _Tool_Logger__WEBPACK_IMPORTED_MODULE_0__["default"].Info("[NativeHost::start] connectNative: ".concat(nativeHostKey));
              }
              this.conn.onDisconnect.addListener(function () {
                _this2.disconnected = true;
                if (chrome.runtime.lastError && chrome.runtime.lastError.message) {
                  if (chrome.runtime.lastError.message.indexOf('not found') != -1) {
                    _this2.disconnectedReason = "\u672A\u627E\u5230\u670D\u52A1\uFF0C\u8BF7\u5728\u5F71\u5200\u81EA\u52A8\u5316\u63D2\u4EF6\u5B89\u88C5\u754C\u9762\uFF0C\u91CD\u65B0\u5B89\u88C5\u81EA\u52A8\u5316\u6269\u5C55\u7A0B\u5E8F";
                  } else {
                    _this2.disconnectedReason = "\u8FDE\u63A5\u65AD\u5F00: ".concat(chrome.runtime.lastError.message, "\uFF0C\u8BF7\u5C1D\u8BD5\u91CD\u542F\u6D4F\u89C8\u5668");
                  }
                } else {
                  _this2.disconnectedReason = "\u8FDE\u63A5\u65AD\u5F00: \u672A\u77E5\u9519\u8BEF\uFF0C\u8BF7\u5C1D\u8BD5\u91CD\u542F\u6D4F\u89C8\u5668";
                }
                _Tool_Logger__WEBPACK_IMPORTED_MODULE_0__["default"].Error("".concat(_this2.disconnectedReason));
              });
            case 5:
            case "end":
              return _context.stop();
          }
        }, _callee, this);
      }));
      function Start(_x) {
        return _Start.apply(this, arguments);
      }
      return Start;
    }())
  }, {
    key: "CheckConnection",
    value: function CheckConnection() {
      if (this.disconnected) _Tool_Logger__WEBPACK_IMPORTED_MODULE_0__["default"].Error(this.disconnectedReason);
      return !this.disconnected;
    }
  }, {
    key: "Request",
    value: function Request(method, params) {
      if (this.CheckConnection()) this.conn.postMessage({
        method: method,
        params: params
      });
    }
  }, {
    key: "GetBridgeInterfaceVersion",
    value: function GetBridgeInterfaceVersion() {
      return this.bridgeInterfaceVersion;
    }

    /**
     * 
     * @returns Promise<Port | null>
     */
  }, {
    key: "_StartNativeHost_v2",
    value: (function () {
      var _StartNativeHost_v = _asyncToGenerator( /*#__PURE__*/_regeneratorRuntime().mark(function _callee2(msgHandler) {
        var _this3 = this;
        return _regeneratorRuntime().wrap(function _callee2$(_context2) {
          while (1) switch (_context2.prev = _context2.next) {
            case 0:
              return _context2.abrupt("return", new Promise(function (resolve) {
                var nativeHostKey = 'shadowbot.chrome.bridge_v2';
                var port = chrome.runtime.connectNative(nativeHostKey);
                _Tool_Logger__WEBPACK_IMPORTED_MODULE_0__["default"].Info("[NativeHost::startNativeHost_v2] connectNative: ".concat(nativeHostKey));

                // 临时的消息监听器
                var _onGetVersion = null;
                var _onDisconnect = null;
                var hasResolve = false;
                _onGetVersion = function onGetVersion(message) {
                  if (message && message.method == 'Bridge.GetInterfaceVersion') {
                    _Tool_Logger__WEBPACK_IMPORTED_MODULE_0__["default"].Info("[NativeHost::startNativeHost_v2] onGetInterfaceVersion: ".concat(message.params.version));
                    port.onMessage.removeListener(_onGetVersion);
                    port.onDisconnect.removeListener(_onDisconnect);
                    hasResolve = true;
                    _this3.bridgeInterfaceVersion = message.params.version;
                    return resolve(port);
                  }
                };
                _onDisconnect = function onDisconnect() {
                  _Tool_Logger__WEBPACK_IMPORTED_MODULE_0__["default"].Info("[NativeHost::startNativeHost_v2] onDisconnect error: ".concat(chrome.runtime.lastError ? chrome.runtime.lastError.message : ''));
                  port.onMessage.removeListener(_onGetVersion);
                  port.onDisconnect.removeListener(_onDisconnect);
                  hasResolve = true;
                  return resolve(null);
                };
                port.onMessage.addListener(_onGetVersion);
                port.onDisconnect.addListener(_onDisconnect);
                port.onMessage.addListener(msgHandler);
                _Tool_Logger__WEBPACK_IMPORTED_MODULE_0__["default"].Info("[NativeHost::startNativeHost_v2] request: BridgeGetInterfaceVersion");
                port.postMessage({
                  method: 'BridgeGetInterfaceVersion',
                  params: {}
                });

                // 这种只会发生在极端情况下：新版本影刀安装了shadowbot.chrome.bridge_v2，然后又使用旧版本影刀重装shadowbot.chrome.bridge，此时由于注册表残留，会连接到未实现"BridgeGetVersion"接口的bridge, 因此会卡死
                setTimeout(function () {
                  if (!hasResolve) {
                    // 无需任何处理，提示错误即可
                    _Tool_Logger__WEBPACK_IMPORTED_MODULE_0__["default"].Error("\u63D2\u4EF6\u7248\u672C\u4E0D\u5339\u914D\uFF0C\u8BF7\u5728\u5F71\u5200\u81EA\u52A8\u5316\u63D2\u4EF6\u5B89\u88C5\u754C\u9762\uFF0C\u91CD\u65B0\u5B89\u88C5\u81EA\u52A8\u5316\u6269\u5C55\u7A0B\u5E8F");
                  }
                }, 10000);
              }));
            case 1:
            case "end":
              return _context2.stop();
          }
        }, _callee2);
      }));
      function _StartNativeHost_v2(_x2) {
        return _StartNativeHost_v.apply(this, arguments);
      }
      return _StartNativeHost_v2;
    }())
  }]);
}();


/***/ }),
/* 10 */
/*!***************************************!*\
  !*** ./Src/Tool/ReturnCallbackMap.js ***!
  \***************************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "default", function() { return ReturnCallbackMap; });
function _typeof(o) { "@babel/helpers - typeof"; return _typeof = "function" == typeof Symbol && "symbol" == typeof Symbol.iterator ? function (o) { return typeof o; } : function (o) { return o && "function" == typeof Symbol && o.constructor === Symbol && o !== Symbol.prototype ? "symbol" : typeof o; }, _typeof(o); }
function _classCallCheck(a, n) { if (!(a instanceof n)) throw new TypeError("Cannot call a class as a function"); }
function _defineProperties(e, r) { for (var t = 0; t < r.length; t++) { var o = r[t]; o.enumerable = o.enumerable || !1, o.configurable = !0, "value" in o && (o.writable = !0), Object.defineProperty(e, _toPropertyKey(o.key), o); } }
function _createClass(e, r, t) { return r && _defineProperties(e.prototype, r), t && _defineProperties(e, t), Object.defineProperty(e, "prototype", { writable: !1 }), e; }
function _toPropertyKey(t) { var i = _toPrimitive(t, "string"); return "symbol" == _typeof(i) ? i : i + ""; }
function _toPrimitive(t, r) { if ("object" != _typeof(t) || !t) return t; var e = t[Symbol.toPrimitive]; if (void 0 !== e) { var i = e.call(t, r || "default"); if ("object" != _typeof(i)) return i; throw new TypeError("@@toPrimitive must return a primitive value."); } return ("string" === r ? String : Number)(t); }
var ReturnCallbackMap = /*#__PURE__*/function () {
  function ReturnCallbackMap() {
    _classCallCheck(this, ReturnCallbackMap);
    this.requestId = 0;
    this.returnMap = {};
  }
  return _createClass(ReturnCallbackMap, [{
    key: "RegisterReturnCallback",
    value: function RegisterReturnCallback(returnFunc) {
      this.requestId++;
      this.returnMap[this.requestId] = returnFunc;
      return this.requestId;
    }
  }, {
    key: "HandleReturnCallback",
    value: function HandleReturnCallback(returnId, params) {
      var returnFunc = this.returnMap[returnId];
      if (returnFunc) {
        returnFunc(params);
        delete this.returnMap[returnId];
      }
    }
  }]);
}();


/***/ }),
/* 11 */
/*!********************************!*\
  !*** ./Src/Handler/Factory.js ***!
  \********************************/
/*! exports provided: CreateWindowHandler */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "CreateWindowHandler", function() { return CreateWindowHandler; });
/* harmony import */ var _Tool_BrowserTools__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! ../Tool/BrowserTools */ 3);
/* harmony import */ var _WindowHandler_v1_WindowHandler_win__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(/*! ./WindowHandler_v1/WindowHandler.win */ 12);
/* harmony import */ var _WindowHandler_v2_WindowHandler_win__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(/*! ./WindowHandler_v2/WindowHandler.win */ 14);
/* harmony import */ var _WindowHandler_v1_WindowHandler_mac__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(/*! ./WindowHandler_v1/WindowHandler.mac */ 15);
/* harmony import */ var _Tool_Version__WEBPACK_IMPORTED_MODULE_4__ = __webpack_require__(/*! ../Tool/Version */ 16);






/**
 * 
 * @param {*} loaderPortable 
 * @returns WindowHandlerBase | null
 */
function CreateWindowHandler(loaderPortable) {
  var bridgeInterfaceVersion = loaderPortable.nativeHost.GetBridgeInterfaceVersion();
  if (_Tool_BrowserTools__WEBPACK_IMPORTED_MODULE_0__["default"].GetPlatform() === 'win32') {
    if (Object(_Tool_Version__WEBPACK_IMPORTED_MODULE_4__["CompareVersion"])(bridgeInterfaceVersion, '3.1') < 0) return new _WindowHandler_v1_WindowHandler_win__WEBPACK_IMPORTED_MODULE_1__["default"](loaderPortable);else return new _WindowHandler_v2_WindowHandler_win__WEBPACK_IMPORTED_MODULE_2__["default"](loaderPortable);
  } else if (_Tool_BrowserTools__WEBPACK_IMPORTED_MODULE_0__["default"].GetPlatform() === 'darwin') {
    return new _WindowHandler_v1_WindowHandler_mac__WEBPACK_IMPORTED_MODULE_3__["default"](loaderPortable);
  } else {
    // linux 无需考虑兼容性，不需要新版v3插件支持旧版nativeHost
    // TODO 若需要改实现时，新增WindowHandlerLinux_v2
    return new _WindowHandler_v2_WindowHandler_win__WEBPACK_IMPORTED_MODULE_2__["default"](loaderPortable);
  }
}

/***/ }),
/* 12 */
/*!***********************************************************!*\
  !*** ./Src/Handler/WindowHandler_v1/WindowHandler.win.js ***!
  \***********************************************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* harmony import */ var _WindowHandler__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! ../WindowHandler */ 13);
/* harmony import */ var _Tool_Logger__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(/*! ../../Tool/Logger */ 1);
function _typeof(o) { "@babel/helpers - typeof"; return _typeof = "function" == typeof Symbol && "symbol" == typeof Symbol.iterator ? function (o) { return typeof o; } : function (o) { return o && "function" == typeof Symbol && o.constructor === Symbol && o !== Symbol.prototype ? "symbol" : typeof o; }, _typeof(o); }
function _createForOfIteratorHelper(r, e) { var t = "undefined" != typeof Symbol && r[Symbol.iterator] || r["@@iterator"]; if (!t) { if (Array.isArray(r) || (t = _unsupportedIterableToArray(r)) || e && r && "number" == typeof r.length) { t && (r = t); var _n = 0, F = function F() {}; return { s: F, n: function n() { return _n >= r.length ? { done: !0 } : { done: !1, value: r[_n++] }; }, e: function e(r) { throw r; }, f: F }; } throw new TypeError("Invalid attempt to iterate non-iterable instance.\nIn order to be iterable, non-array objects must have a [Symbol.iterator]() method."); } var o, a = !0, u = !1; return { s: function s() { t = t.call(r); }, n: function n() { var r = t.next(); return a = r.done, r; }, e: function e(r) { u = !0, o = r; }, f: function f() { try { a || null == t["return"] || t["return"](); } finally { if (u) throw o; } } }; }
function _unsupportedIterableToArray(r, a) { if (r) { if ("string" == typeof r) return _arrayLikeToArray(r, a); var t = {}.toString.call(r).slice(8, -1); return "Object" === t && r.constructor && (t = r.constructor.name), "Map" === t || "Set" === t ? Array.from(r) : "Arguments" === t || /^(?:Ui|I)nt(?:8|16|32)(?:Clamped)?Array$/.test(t) ? _arrayLikeToArray(r, a) : void 0; } }
function _arrayLikeToArray(r, a) { (null == a || a > r.length) && (a = r.length); for (var e = 0, n = Array(a); e < a; e++) n[e] = r[e]; return n; }
function _regeneratorRuntime() { "use strict"; /*! regenerator-runtime -- Copyright (c) 2014-present, Facebook, Inc. -- license (MIT): https://github.com/facebook/regenerator/blob/main/LICENSE */ _regeneratorRuntime = function _regeneratorRuntime() { return e; }; var t, e = {}, r = Object.prototype, n = r.hasOwnProperty, o = Object.defineProperty || function (t, e, r) { t[e] = r.value; }, i = "function" == typeof Symbol ? Symbol : {}, a = i.iterator || "@@iterator", c = i.asyncIterator || "@@asyncIterator", u = i.toStringTag || "@@toStringTag"; function define(t, e, r) { return Object.defineProperty(t, e, { value: r, enumerable: !0, configurable: !0, writable: !0 }), t[e]; } try { define({}, ""); } catch (t) { define = function define(t, e, r) { return t[e] = r; }; } function wrap(t, e, r, n) { var i = e && e.prototype instanceof Generator ? e : Generator, a = Object.create(i.prototype), c = new Context(n || []); return o(a, "_invoke", { value: makeInvokeMethod(t, r, c) }), a; } function tryCatch(t, e, r) { try { return { type: "normal", arg: t.call(e, r) }; } catch (t) { return { type: "throw", arg: t }; } } e.wrap = wrap; var h = "suspendedStart", l = "suspendedYield", f = "executing", s = "completed", y = {}; function Generator() {} function GeneratorFunction() {} function GeneratorFunctionPrototype() {} var p = {}; define(p, a, function () { return this; }); var d = Object.getPrototypeOf, v = d && d(d(values([]))); v && v !== r && n.call(v, a) && (p = v); var g = GeneratorFunctionPrototype.prototype = Generator.prototype = Object.create(p); function defineIteratorMethods(t) { ["next", "throw", "return"].forEach(function (e) { define(t, e, function (t) { return this._invoke(e, t); }); }); } function AsyncIterator(t, e) { function invoke(r, o, i, a) { var c = tryCatch(t[r], t, o); if ("throw" !== c.type) { var u = c.arg, h = u.value; return h && "object" == _typeof(h) && n.call(h, "__await") ? e.resolve(h.__await).then(function (t) { invoke("next", t, i, a); }, function (t) { invoke("throw", t, i, a); }) : e.resolve(h).then(function (t) { u.value = t, i(u); }, function (t) { return invoke("throw", t, i, a); }); } a(c.arg); } var r; o(this, "_invoke", { value: function value(t, n) { function callInvokeWithMethodAndArg() { return new e(function (e, r) { invoke(t, n, e, r); }); } return r = r ? r.then(callInvokeWithMethodAndArg, callInvokeWithMethodAndArg) : callInvokeWithMethodAndArg(); } }); } function makeInvokeMethod(e, r, n) { var o = h; return function (i, a) { if (o === f) throw Error("Generator is already running"); if (o === s) { if ("throw" === i) throw a; return { value: t, done: !0 }; } for (n.method = i, n.arg = a;;) { var c = n.delegate; if (c) { var u = maybeInvokeDelegate(c, n); if (u) { if (u === y) continue; return u; } } if ("next" === n.method) n.sent = n._sent = n.arg;else if ("throw" === n.method) { if (o === h) throw o = s, n.arg; n.dispatchException(n.arg); } else "return" === n.method && n.abrupt("return", n.arg); o = f; var p = tryCatch(e, r, n); if ("normal" === p.type) { if (o = n.done ? s : l, p.arg === y) continue; return { value: p.arg, done: n.done }; } "throw" === p.type && (o = s, n.method = "throw", n.arg = p.arg); } }; } function maybeInvokeDelegate(e, r) { var n = r.method, o = e.iterator[n]; if (o === t) return r.delegate = null, "throw" === n && e.iterator["return"] && (r.method = "return", r.arg = t, maybeInvokeDelegate(e, r), "throw" === r.method) || "return" !== n && (r.method = "throw", r.arg = new TypeError("The iterator does not provide a '" + n + "' method")), y; var i = tryCatch(o, e.iterator, r.arg); if ("throw" === i.type) return r.method = "throw", r.arg = i.arg, r.delegate = null, y; var a = i.arg; return a ? a.done ? (r[e.resultName] = a.value, r.next = e.nextLoc, "return" !== r.method && (r.method = "next", r.arg = t), r.delegate = null, y) : a : (r.method = "throw", r.arg = new TypeError("iterator result is not an object"), r.delegate = null, y); } function pushTryEntry(t) { var e = { tryLoc: t[0] }; 1 in t && (e.catchLoc = t[1]), 2 in t && (e.finallyLoc = t[2], e.afterLoc = t[3]), this.tryEntries.push(e); } function resetTryEntry(t) { var e = t.completion || {}; e.type = "normal", delete e.arg, t.completion = e; } function Context(t) { this.tryEntries = [{ tryLoc: "root" }], t.forEach(pushTryEntry, this), this.reset(!0); } function values(e) { if (e || "" === e) { var r = e[a]; if (r) return r.call(e); if ("function" == typeof e.next) return e; if (!isNaN(e.length)) { var o = -1, i = function next() { for (; ++o < e.length;) if (n.call(e, o)) return next.value = e[o], next.done = !1, next; return next.value = t, next.done = !0, next; }; return i.next = i; } } throw new TypeError(_typeof(e) + " is not iterable"); } return GeneratorFunction.prototype = GeneratorFunctionPrototype, o(g, "constructor", { value: GeneratorFunctionPrototype, configurable: !0 }), o(GeneratorFunctionPrototype, "constructor", { value: GeneratorFunction, configurable: !0 }), GeneratorFunction.displayName = define(GeneratorFunctionPrototype, u, "GeneratorFunction"), e.isGeneratorFunction = function (t) { var e = "function" == typeof t && t.constructor; return !!e && (e === GeneratorFunction || "GeneratorFunction" === (e.displayName || e.name)); }, e.mark = function (t) { return Object.setPrototypeOf ? Object.setPrototypeOf(t, GeneratorFunctionPrototype) : (t.__proto__ = GeneratorFunctionPrototype, define(t, u, "GeneratorFunction")), t.prototype = Object.create(g), t; }, e.awrap = function (t) { return { __await: t }; }, defineIteratorMethods(AsyncIterator.prototype), define(AsyncIterator.prototype, c, function () { return this; }), e.AsyncIterator = AsyncIterator, e.async = function (t, r, n, o, i) { void 0 === i && (i = Promise); var a = new AsyncIterator(wrap(t, r, n, o), i); return e.isGeneratorFunction(r) ? a : a.next().then(function (t) { return t.done ? t.value : a.next(); }); }, defineIteratorMethods(g), define(g, u, "Generator"), define(g, a, function () { return this; }), define(g, "toString", function () { return "[object Generator]"; }), e.keys = function (t) { var e = Object(t), r = []; for (var n in e) r.push(n); return r.reverse(), function next() { for (; r.length;) { var t = r.pop(); if (t in e) return next.value = t, next.done = !1, next; } return next.done = !0, next; }; }, e.values = values, Context.prototype = { constructor: Context, reset: function reset(e) { if (this.prev = 0, this.next = 0, this.sent = this._sent = t, this.done = !1, this.delegate = null, this.method = "next", this.arg = t, this.tryEntries.forEach(resetTryEntry), !e) for (var r in this) "t" === r.charAt(0) && n.call(this, r) && !isNaN(+r.slice(1)) && (this[r] = t); }, stop: function stop() { this.done = !0; var t = this.tryEntries[0].completion; if ("throw" === t.type) throw t.arg; return this.rval; }, dispatchException: function dispatchException(e) { if (this.done) throw e; var r = this; function handle(n, o) { return a.type = "throw", a.arg = e, r.next = n, o && (r.method = "next", r.arg = t), !!o; } for (var o = this.tryEntries.length - 1; o >= 0; --o) { var i = this.tryEntries[o], a = i.completion; if ("root" === i.tryLoc) return handle("end"); if (i.tryLoc <= this.prev) { var c = n.call(i, "catchLoc"), u = n.call(i, "finallyLoc"); if (c && u) { if (this.prev < i.catchLoc) return handle(i.catchLoc, !0); if (this.prev < i.finallyLoc) return handle(i.finallyLoc); } else if (c) { if (this.prev < i.catchLoc) return handle(i.catchLoc, !0); } else { if (!u) throw Error("try statement without catch or finally"); if (this.prev < i.finallyLoc) return handle(i.finallyLoc); } } } }, abrupt: function abrupt(t, e) { for (var r = this.tryEntries.length - 1; r >= 0; --r) { var o = this.tryEntries[r]; if (o.tryLoc <= this.prev && n.call(o, "finallyLoc") && this.prev < o.finallyLoc) { var i = o; break; } } i && ("break" === t || "continue" === t) && i.tryLoc <= e && e <= i.finallyLoc && (i = null); var a = i ? i.completion : {}; return a.type = t, a.arg = e, i ? (this.method = "next", this.next = i.finallyLoc, y) : this.complete(a); }, complete: function complete(t, e) { if ("throw" === t.type) throw t.arg; return "break" === t.type || "continue" === t.type ? this.next = t.arg : "return" === t.type ? (this.rval = this.arg = t.arg, this.method = "return", this.next = "end") : "normal" === t.type && e && (this.next = e), y; }, finish: function finish(t) { for (var e = this.tryEntries.length - 1; e >= 0; --e) { var r = this.tryEntries[e]; if (r.finallyLoc === t) return this.complete(r.completion, r.afterLoc), resetTryEntry(r), y; } }, "catch": function _catch(t) { for (var e = this.tryEntries.length - 1; e >= 0; --e) { var r = this.tryEntries[e]; if (r.tryLoc === t) { var n = r.completion; if ("throw" === n.type) { var o = n.arg; resetTryEntry(r); } return o; } } throw Error("illegal catch attempt"); }, delegateYield: function delegateYield(e, r, n) { return this.delegate = { iterator: values(e), resultName: r, nextLoc: n }, "next" === this.method && (this.arg = t), y; } }, e; }
function asyncGeneratorStep(n, t, e, r, o, a, c) { try { var i = n[a](c), u = i.value; } catch (n) { return void e(n); } i.done ? t(u) : Promise.resolve(u).then(r, o); }
function _asyncToGenerator(n) { return function () { var t = this, e = arguments; return new Promise(function (r, o) { var a = n.apply(t, e); function _next(n) { asyncGeneratorStep(a, r, o, _next, _throw, "next", n); } function _throw(n) { asyncGeneratorStep(a, r, o, _next, _throw, "throw", n); } _next(void 0); }); }; }
function _classCallCheck(a, n) { if (!(a instanceof n)) throw new TypeError("Cannot call a class as a function"); }
function _defineProperties(e, r) { for (var t = 0; t < r.length; t++) { var o = r[t]; o.enumerable = o.enumerable || !1, o.configurable = !0, "value" in o && (o.writable = !0), Object.defineProperty(e, _toPropertyKey(o.key), o); } }
function _createClass(e, r, t) { return r && _defineProperties(e.prototype, r), t && _defineProperties(e, t), Object.defineProperty(e, "prototype", { writable: !1 }), e; }
function _toPropertyKey(t) { var i = _toPrimitive(t, "string"); return "symbol" == _typeof(i) ? i : i + ""; }
function _toPrimitive(t, r) { if ("object" != _typeof(t) || !t) return t; var e = t[Symbol.toPrimitive]; if (void 0 !== e) { var i = e.call(t, r || "default"); if ("object" != _typeof(i)) return i; throw new TypeError("@@toPrimitive must return a primitive value."); } return ("string" === r ? String : Number)(t); }
function _callSuper(t, o, e) { return o = _getPrototypeOf(o), _possibleConstructorReturn(t, _isNativeReflectConstruct() ? Reflect.construct(o, e || [], _getPrototypeOf(t).constructor) : o.apply(t, e)); }
function _possibleConstructorReturn(t, e) { if (e && ("object" == _typeof(e) || "function" == typeof e)) return e; if (void 0 !== e) throw new TypeError("Derived constructors may only return object or undefined"); return _assertThisInitialized(t); }
function _assertThisInitialized(e) { if (void 0 === e) throw new ReferenceError("this hasn't been initialised - super() hasn't been called"); return e; }
function _isNativeReflectConstruct() { try { var t = !Boolean.prototype.valueOf.call(Reflect.construct(Boolean, [], function () {})); } catch (t) {} return (_isNativeReflectConstruct = function _isNativeReflectConstruct() { return !!t; })(); }
function _getPrototypeOf(t) { return _getPrototypeOf = Object.setPrototypeOf ? Object.getPrototypeOf.bind() : function (t) { return t.__proto__ || Object.getPrototypeOf(t); }, _getPrototypeOf(t); }
function _inherits(t, e) { if ("function" != typeof e && null !== e) throw new TypeError("Super expression must either be null or a function"); t.prototype = Object.create(e && e.prototype, { constructor: { value: t, writable: !0, configurable: !0 } }), Object.defineProperty(t, "prototype", { writable: !1 }), e && _setPrototypeOf(t, e); }
function _setPrototypeOf(t, e) { return _setPrototypeOf = Object.setPrototypeOf ? Object.setPrototypeOf.bind() : function (t, e) { return t.__proto__ = e, t; }, _setPrototypeOf(t, e); }


var WindowHandler = /*#__PURE__*/function (_WindowHandlerBase) {
  function WindowHandler(loaderPortable) {
    var _this;
    _classCallCheck(this, WindowHandler);
    _this = _callSuper(this, WindowHandler, [loaderPortable]);
    _this.__InitWindowHandler();
    return _this;
  }
  _inherits(WindowHandler, _WindowHandlerBase);
  return _createClass(WindowHandler, [{
    key: "__InitWindowHandler",
    value: function __InitWindowHandler() {
      var _this2 = this;
      this.handlers['Window.SetHwnd'] = function (params) {
        _Tool_Logger__WEBPACK_IMPORTED_MODULE_1__["default"].Info("Window.SetHwnd: ".concat(JSON.stringify(params)));
        var wndId = params['wndId'];
        wnd2HwndDict[wndId] = params['hwnd'];
        chrome.windows.get(wndId, {
          populate: true
        }, function (window) {
          window === null || window === void 0 || window.tabs.every(function (tab) {
            if (!tab.title.includes(wndId.toString())) return;
            chrome.scripting.executeScript({
              target: {
                tabId: tab.id
              },
              func: function func(windowId) {
                return document.title = document.title.slice(0, document.title.length - windowId.toString().length - "WindowId: ".length);
              },
              args: [wndId]
            })["catch"](function (e) {
              console.error(e);
            });
          });
        });
      };
      this.handlers['Bridge.AdjustConflictWnds'] = function (params) {
        // 发生冲突时，为发生冲突的tab页改名，增加后缀 windowId
        _Tool_Logger__WEBPACK_IMPORTED_MODULE_1__["default"].Info("Bridge.AdjustConflictWnds params: ", params);
        var wndId = params['wndId'];
        var addSuffixToTitle = /*#__PURE__*/function () {
          var _ref = _asyncToGenerator( /*#__PURE__*/_regeneratorRuntime().mark(function _callee(tabId) {
            var suffix;
            return _regeneratorRuntime().wrap(function _callee$(_context) {
              while (1) switch (_context.prev = _context.next) {
                case 0:
                  _Tool_Logger__WEBPACK_IMPORTED_MODULE_1__["default"].Info("add suffix for ".concat(tabId));
                  suffix = "WindowId: ".concat(wndId);
                  chrome.scripting.executeScript({
                    target: {
                      tabId: tabId
                    },
                    func: function func(suffix) {
                      if (!document.title.includes(suffix)) document.title += suffix;
                    },
                    args: [suffix]
                  })["catch"](function (e) {
                    _Tool_Logger__WEBPACK_IMPORTED_MODULE_1__["default"].Info(e);
                  });
                  _this2.WindowRenamed(wndId);
                case 4:
                case "end":
                  return _context.stop();
              }
            }, _callee);
          }));
          return function addSuffixToTitle(_x) {
            return _ref.apply(this, arguments);
          };
        }();

        // 防止网页更新造成 Title 变动导致匹配失败
        // 当 Tab 页更新时调用
        var updatedHandler = /*#__PURE__*/function () {
          var _ref2 = _asyncToGenerator( /*#__PURE__*/_regeneratorRuntime().mark(function _callee2(tabId, changeInfo, tab) {
            return _regeneratorRuntime().wrap(function _callee2$(_context2) {
              while (1) switch (_context2.prev = _context2.next) {
                case 0:
                  if (!(changeInfo.status !== "complete" || tab.active === "false")) {
                    _context2.next = 2;
                    break;
                  }
                  return _context2.abrupt("return");
                case 2:
                  if (!(Object.keys(wnd2HwndDict).indexOf(tab.windowId.toString()) !== -1)) {
                    _context2.next = 5;
                    break;
                  }
                  chrome.tabs.onUpdated.removeListener(updatedHandler);
                  return _context2.abrupt("return");
                case 5:
                  if (!tab.title.includes(wndId.toString())) {
                    _context2.next = 7;
                    break;
                  }
                  return _context2.abrupt("return");
                case 7:
                  addSuffixToTitle(tabId);
                case 8:
                case "end":
                  return _context2.stop();
              }
            }, _callee2);
          }));
          return function updatedHandler(_x2, _x3, _x4) {
            return _ref2.apply(this, arguments);
          };
        }();
        chrome.tabs.onUpdated.addListener(updatedHandler);

        // 当 Tab 页激活时调用
        var activatedHandler = /*#__PURE__*/function () {
          var _ref3 = _asyncToGenerator( /*#__PURE__*/_regeneratorRuntime().mark(function _callee3(activeInfo) {
            var tab;
            return _regeneratorRuntime().wrap(function _callee3$(_context3) {
              while (1) switch (_context3.prev = _context3.next) {
                case 0:
                  if (!(Object.keys(wnd2HwndDict).indexOf(activeInfo.windowId.toString()) != -1)) {
                    _context3.next = 3;
                    break;
                  }
                  chrome.tabs.onActivated.removeListener(activatedHandler);
                  return _context3.abrupt("return");
                case 3:
                  _context3.next = 5;
                  return chrome.tabs.get(activeInfo.tabId);
                case 5:
                  tab = _context3.sent;
                  if (!tab.title.includes(wndId.toString())) {
                    _context3.next = 8;
                    break;
                  }
                  return _context3.abrupt("return");
                case 8:
                  addSuffixToTitle(activeInfo.tabId);
                case 9:
                case "end":
                  return _context3.stop();
              }
            }, _callee3);
          }));
          return function activatedHandler(_x5) {
            return _ref3.apply(this, arguments);
          };
        }();
        chrome.tabs.onActivated.addListener(activatedHandler);
        chrome.windows.get(wndId, {
          populate: true
        }, function (window) {
          var activeTab = window === null || window === void 0 ? void 0 : window.tabs.filter(function (tab) {
            return tab.active === true;
          })[0];
          addSuffixToTitle(activeTab.id);
        });
      };
    }
  }, {
    key: "Init",
    value: function () {
      var _Init = _asyncToGenerator( /*#__PURE__*/_regeneratorRuntime().mark(function _callee4() {
        var _this3 = this;
        return _regeneratorRuntime().wrap(function _callee4$(_context4) {
          while (1) switch (_context4.prev = _context4.next) {
            case 0:
              return _context4.abrupt("return", new Promise(function (resolve) {
                chrome.windows.getAll({
                  populate: true
                }, function (wnds) {
                  // 获取所有窗口后再监听窗口的创建（如果获取窗口前监听窗口的创建，service_worker可能会先触发窗口创建事件，此时再获取所有窗口，导致同一个窗口注册两次）
                  // chrome105存在此类情况：获取的所有窗口中有目标窗口，然而后续目标窗口的创建事件仍然会触发。

                  // 通过Set来解决重复注册问题
                  var firstRegisteredWndIdSet = new Set(wnds.map(function (wnd) {
                    return wnd.id;
                  }));
                  chrome.windows.onCreated.addListener(function (wnd) {
                    if (_this3.IsAutomationWnd(wnd)) {
                      if (!firstRegisteredWndIdSet.has(wnd.id)) _this3.WindowCreated(wnd.id);else _Tool_Logger__WEBPACK_IMPORTED_MODULE_1__["default"].Info("[WindowHandler::Init] ignore already registered wndid: ".concat(wnd.id));
                    }
                  });
                  chrome.windows.onRemoved.addListener(function (wndId) {
                    _this3.WindowRemoved(wndId);
                    delete wnd2HwndDict[wndId];
                  });
                  var wndsCount = 0;
                  var lastWndId = 0;
                  var _iterator = _createForOfIteratorHelper(wnds),
                    _step;
                  try {
                    for (_iterator.s(); !(_step = _iterator.n()).done;) {
                      var wnd = _step.value;
                      if (_this3.IsAutomationWnd(wnd)) {
                        if (++wndsCount === 2) break;
                        lastWndId = wnd.id;
                      }
                    }
                  } catch (err) {
                    _iterator.e(err);
                  } finally {
                    _iterator.f();
                  }
                  if (wndsCount === 1) {
                    _this3.WindowCreated(lastWndId);
                  } else {
                    var wndIds = wnds.filter(function (wnd) {
                      return _this3.IsAutomationWnd(wnd);
                    }).map(function (wnd) {
                      return wnd.id;
                    });
                    _Tool_Logger__WEBPACK_IMPORTED_MODULE_1__["default"].Info("[WindowHandler::Init] detect multi automation windows:", wndIds);
                  }
                  _this3.WindowMultipleCreated(wnds);

                  // 历史上，并不会等待所有窗口注册完毕，因此这里直接 resolve
                  return resolve();
                });
              }));
            case 1:
            case "end":
              return _context4.stop();
          }
        }, _callee4);
      }));
      function Init() {
        return _Init.apply(this, arguments);
      }
      return Init;
    }()
  }, {
    key: "WindowMultipleCreated",
    value: function WindowMultipleCreated(wnds) {
      var _this4 = this;
      if (wnds.length > 1) {
        _Tool_Logger__WEBPACK_IMPORTED_MODULE_1__["default"].Info("WindowMultipleCreated wnds: ", wnds);
        var getWndInfo = function getWndInfo(wnd) {
          var _wnd$left, _wnd$top, _wnd$width, _wnd$height, _wnd$tabs$filter$0$ur, _wnd$tabs;
          var wndId = wnd.id;
          var left = (_wnd$left = wnd.left) !== null && _wnd$left !== void 0 ? _wnd$left : 0;
          var top = (_wnd$top = wnd.top) !== null && _wnd$top !== void 0 ? _wnd$top : 0;
          var width = (_wnd$width = wnd.width) !== null && _wnd$width !== void 0 ? _wnd$width : 0;
          var height = (_wnd$height = wnd.height) !== null && _wnd$height !== void 0 ? _wnd$height : 0;
          var url = (_wnd$tabs$filter$0$ur = (_wnd$tabs = wnd.tabs) === null || _wnd$tabs === void 0 || (_wnd$tabs = _wnd$tabs.filter(function (tab) {
            return tab.active === true;
          })[0]) === null || _wnd$tabs === void 0 ? void 0 : _wnd$tabs.url) !== null && _wnd$tabs$filter$0$ur !== void 0 ? _wnd$tabs$filter$0$ur : "";
          if (url.endsWith("/")) url = url.slice(0, url.length - 1);
          var wndInfo = {
            wndId: wndId,
            url: url,
            left: left,
            top: top,
            width: width,
            height: height
          };
          return wndInfo;
        };
        var wndInfoArray = [];
        wnds.forEach(function (wnd) {
          if (!_this4.IsAutomationWnd(wnd)) return;

          // 防止网页更新造成 URL 变动导致匹配失败
          // 当 Tab 页更新时调用
          var updatedHandler = /*#__PURE__*/function () {
            var _ref4 = _asyncToGenerator( /*#__PURE__*/_regeneratorRuntime().mark(function _callee5(tabId, changeInfo, tab) {
              var newlyWnd, wndInfo;
              return _regeneratorRuntime().wrap(function _callee5$(_context5) {
                while (1) switch (_context5.prev = _context5.next) {
                  case 0:
                    if (!(changeInfo.status !== "complete" || tab.active === "false")) {
                      _context5.next = 2;
                      break;
                    }
                    return _context5.abrupt("return");
                  case 2:
                    if (!(Object.keys(wnd2HwndDict).indexOf(tab.windowId.toString()) !== -1)) {
                      _context5.next = 5;
                      break;
                    }
                    chrome.tabs.onUpdated.removeListener(updatedHandler);
                    return _context5.abrupt("return");
                  case 5:
                    if (!tab.title.includes(wnd.id.toString())) {
                      _context5.next = 7;
                      break;
                    }
                    return _context5.abrupt("return");
                  case 7:
                    _context5.next = 9;
                    return chrome.windows.get(wnd.id, {
                      populate: true
                    });
                  case 9:
                    newlyWnd = _context5.sent;
                    wndInfo = getWndInfo(newlyWnd);
                    _this4.nativeHost.Request('NotifyWindowMultipleCreated', [wndInfo]);
                  case 12:
                  case "end":
                    return _context5.stop();
                }
              }, _callee5);
            }));
            return function updatedHandler(_x6, _x7, _x8) {
              return _ref4.apply(this, arguments);
            };
          }();
          chrome.tabs.onUpdated.addListener(updatedHandler);

          // 当 Tab 页激活时调用
          var activatedHandler = /*#__PURE__*/function () {
            var _ref5 = _asyncToGenerator( /*#__PURE__*/_regeneratorRuntime().mark(function _callee6(activeInfo) {
              var tab, newlyWnd, wndInfo;
              return _regeneratorRuntime().wrap(function _callee6$(_context6) {
                while (1) switch (_context6.prev = _context6.next) {
                  case 0:
                    if (!(Object.keys(wnd2HwndDict).indexOf(activeInfo.windowId.toString()) != -1)) {
                      _context6.next = 3;
                      break;
                    }
                    chrome.tabs.onActivated.removeListener(activatedHandler);
                    return _context6.abrupt("return");
                  case 3:
                    _context6.next = 5;
                    return chrome.tabs.get(activeInfo.tabId);
                  case 5:
                    tab = _context6.sent;
                    if (!tab.title.includes(wnd.id.toString())) {
                      _context6.next = 8;
                      break;
                    }
                    return _context6.abrupt("return");
                  case 8:
                    _context6.next = 10;
                    return chrome.windows.get(wnd.id, {
                      populate: true
                    });
                  case 10:
                    newlyWnd = _context6.sent;
                    wndInfo = getWndInfo(newlyWnd);
                    _this4.nativeHost.Request('NotifyWindowMultipleCreated', [wndInfo]);
                  case 13:
                  case "end":
                    return _context6.stop();
                }
              }, _callee6);
            }));
            return function activatedHandler(_x9) {
              return _ref5.apply(this, arguments);
            };
          }();
          chrome.tabs.onActivated.addListener(activatedHandler);
          wndInfoArray.push(getWndInfo(wnd));
        });
        _Tool_Logger__WEBPACK_IMPORTED_MODULE_1__["default"].Info("NotifyWindowMultipleCreated request: ", wndInfoArray);
        this.nativeHost.Request('NotifyWindowMultipleCreated', wndInfoArray);
      }
    }
  }, {
    key: "WindowRenamed",
    value: function WindowRenamed(wndId) {
      _Tool_Logger__WEBPACK_IMPORTED_MODULE_1__["default"].Info("WindowRenamed id: ", wndId);
      this.nativeHost.Request('NotifyWindowRenamed', wndId);
    }
  }]);
}(_WindowHandler__WEBPACK_IMPORTED_MODULE_0__["WindowHandlerBase"]);
/* harmony default export */ __webpack_exports__["default"] = (WindowHandler);

/***/ }),
/* 13 */
/*!**************************************!*\
  !*** ./Src/Handler/WindowHandler.js ***!
  \**************************************/
/*! exports provided: WindowHandlerBase */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "WindowHandlerBase", function() { return WindowHandlerBase; });
/* harmony import */ var _Tool_Logger__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! ../Tool/Logger */ 1);
function _typeof(o) { "@babel/helpers - typeof"; return _typeof = "function" == typeof Symbol && "symbol" == typeof Symbol.iterator ? function (o) { return typeof o; } : function (o) { return o && "function" == typeof Symbol && o.constructor === Symbol && o !== Symbol.prototype ? "symbol" : typeof o; }, _typeof(o); }
function _regeneratorRuntime() { "use strict"; /*! regenerator-runtime -- Copyright (c) 2014-present, Facebook, Inc. -- license (MIT): https://github.com/facebook/regenerator/blob/main/LICENSE */ _regeneratorRuntime = function _regeneratorRuntime() { return e; }; var t, e = {}, r = Object.prototype, n = r.hasOwnProperty, o = Object.defineProperty || function (t, e, r) { t[e] = r.value; }, i = "function" == typeof Symbol ? Symbol : {}, a = i.iterator || "@@iterator", c = i.asyncIterator || "@@asyncIterator", u = i.toStringTag || "@@toStringTag"; function define(t, e, r) { return Object.defineProperty(t, e, { value: r, enumerable: !0, configurable: !0, writable: !0 }), t[e]; } try { define({}, ""); } catch (t) { define = function define(t, e, r) { return t[e] = r; }; } function wrap(t, e, r, n) { var i = e && e.prototype instanceof Generator ? e : Generator, a = Object.create(i.prototype), c = new Context(n || []); return o(a, "_invoke", { value: makeInvokeMethod(t, r, c) }), a; } function tryCatch(t, e, r) { try { return { type: "normal", arg: t.call(e, r) }; } catch (t) { return { type: "throw", arg: t }; } } e.wrap = wrap; var h = "suspendedStart", l = "suspendedYield", f = "executing", s = "completed", y = {}; function Generator() {} function GeneratorFunction() {} function GeneratorFunctionPrototype() {} var p = {}; define(p, a, function () { return this; }); var d = Object.getPrototypeOf, v = d && d(d(values([]))); v && v !== r && n.call(v, a) && (p = v); var g = GeneratorFunctionPrototype.prototype = Generator.prototype = Object.create(p); function defineIteratorMethods(t) { ["next", "throw", "return"].forEach(function (e) { define(t, e, function (t) { return this._invoke(e, t); }); }); } function AsyncIterator(t, e) { function invoke(r, o, i, a) { var c = tryCatch(t[r], t, o); if ("throw" !== c.type) { var u = c.arg, h = u.value; return h && "object" == _typeof(h) && n.call(h, "__await") ? e.resolve(h.__await).then(function (t) { invoke("next", t, i, a); }, function (t) { invoke("throw", t, i, a); }) : e.resolve(h).then(function (t) { u.value = t, i(u); }, function (t) { return invoke("throw", t, i, a); }); } a(c.arg); } var r; o(this, "_invoke", { value: function value(t, n) { function callInvokeWithMethodAndArg() { return new e(function (e, r) { invoke(t, n, e, r); }); } return r = r ? r.then(callInvokeWithMethodAndArg, callInvokeWithMethodAndArg) : callInvokeWithMethodAndArg(); } }); } function makeInvokeMethod(e, r, n) { var o = h; return function (i, a) { if (o === f) throw Error("Generator is already running"); if (o === s) { if ("throw" === i) throw a; return { value: t, done: !0 }; } for (n.method = i, n.arg = a;;) { var c = n.delegate; if (c) { var u = maybeInvokeDelegate(c, n); if (u) { if (u === y) continue; return u; } } if ("next" === n.method) n.sent = n._sent = n.arg;else if ("throw" === n.method) { if (o === h) throw o = s, n.arg; n.dispatchException(n.arg); } else "return" === n.method && n.abrupt("return", n.arg); o = f; var p = tryCatch(e, r, n); if ("normal" === p.type) { if (o = n.done ? s : l, p.arg === y) continue; return { value: p.arg, done: n.done }; } "throw" === p.type && (o = s, n.method = "throw", n.arg = p.arg); } }; } function maybeInvokeDelegate(e, r) { var n = r.method, o = e.iterator[n]; if (o === t) return r.delegate = null, "throw" === n && e.iterator["return"] && (r.method = "return", r.arg = t, maybeInvokeDelegate(e, r), "throw" === r.method) || "return" !== n && (r.method = "throw", r.arg = new TypeError("The iterator does not provide a '" + n + "' method")), y; var i = tryCatch(o, e.iterator, r.arg); if ("throw" === i.type) return r.method = "throw", r.arg = i.arg, r.delegate = null, y; var a = i.arg; return a ? a.done ? (r[e.resultName] = a.value, r.next = e.nextLoc, "return" !== r.method && (r.method = "next", r.arg = t), r.delegate = null, y) : a : (r.method = "throw", r.arg = new TypeError("iterator result is not an object"), r.delegate = null, y); } function pushTryEntry(t) { var e = { tryLoc: t[0] }; 1 in t && (e.catchLoc = t[1]), 2 in t && (e.finallyLoc = t[2], e.afterLoc = t[3]), this.tryEntries.push(e); } function resetTryEntry(t) { var e = t.completion || {}; e.type = "normal", delete e.arg, t.completion = e; } function Context(t) { this.tryEntries = [{ tryLoc: "root" }], t.forEach(pushTryEntry, this), this.reset(!0); } function values(e) { if (e || "" === e) { var r = e[a]; if (r) return r.call(e); if ("function" == typeof e.next) return e; if (!isNaN(e.length)) { var o = -1, i = function next() { for (; ++o < e.length;) if (n.call(e, o)) return next.value = e[o], next.done = !1, next; return next.value = t, next.done = !0, next; }; return i.next = i; } } throw new TypeError(_typeof(e) + " is not iterable"); } return GeneratorFunction.prototype = GeneratorFunctionPrototype, o(g, "constructor", { value: GeneratorFunctionPrototype, configurable: !0 }), o(GeneratorFunctionPrototype, "constructor", { value: GeneratorFunction, configurable: !0 }), GeneratorFunction.displayName = define(GeneratorFunctionPrototype, u, "GeneratorFunction"), e.isGeneratorFunction = function (t) { var e = "function" == typeof t && t.constructor; return !!e && (e === GeneratorFunction || "GeneratorFunction" === (e.displayName || e.name)); }, e.mark = function (t) { return Object.setPrototypeOf ? Object.setPrototypeOf(t, GeneratorFunctionPrototype) : (t.__proto__ = GeneratorFunctionPrototype, define(t, u, "GeneratorFunction")), t.prototype = Object.create(g), t; }, e.awrap = function (t) { return { __await: t }; }, defineIteratorMethods(AsyncIterator.prototype), define(AsyncIterator.prototype, c, function () { return this; }), e.AsyncIterator = AsyncIterator, e.async = function (t, r, n, o, i) { void 0 === i && (i = Promise); var a = new AsyncIterator(wrap(t, r, n, o), i); return e.isGeneratorFunction(r) ? a : a.next().then(function (t) { return t.done ? t.value : a.next(); }); }, defineIteratorMethods(g), define(g, u, "Generator"), define(g, a, function () { return this; }), define(g, "toString", function () { return "[object Generator]"; }), e.keys = function (t) { var e = Object(t), r = []; for (var n in e) r.push(n); return r.reverse(), function next() { for (; r.length;) { var t = r.pop(); if (t in e) return next.value = t, next.done = !1, next; } return next.done = !0, next; }; }, e.values = values, Context.prototype = { constructor: Context, reset: function reset(e) { if (this.prev = 0, this.next = 0, this.sent = this._sent = t, this.done = !1, this.delegate = null, this.method = "next", this.arg = t, this.tryEntries.forEach(resetTryEntry), !e) for (var r in this) "t" === r.charAt(0) && n.call(this, r) && !isNaN(+r.slice(1)) && (this[r] = t); }, stop: function stop() { this.done = !0; var t = this.tryEntries[0].completion; if ("throw" === t.type) throw t.arg; return this.rval; }, dispatchException: function dispatchException(e) { if (this.done) throw e; var r = this; function handle(n, o) { return a.type = "throw", a.arg = e, r.next = n, o && (r.method = "next", r.arg = t), !!o; } for (var o = this.tryEntries.length - 1; o >= 0; --o) { var i = this.tryEntries[o], a = i.completion; if ("root" === i.tryLoc) return handle("end"); if (i.tryLoc <= this.prev) { var c = n.call(i, "catchLoc"), u = n.call(i, "finallyLoc"); if (c && u) { if (this.prev < i.catchLoc) return handle(i.catchLoc, !0); if (this.prev < i.finallyLoc) return handle(i.finallyLoc); } else if (c) { if (this.prev < i.catchLoc) return handle(i.catchLoc, !0); } else { if (!u) throw Error("try statement without catch or finally"); if (this.prev < i.finallyLoc) return handle(i.finallyLoc); } } } }, abrupt: function abrupt(t, e) { for (var r = this.tryEntries.length - 1; r >= 0; --r) { var o = this.tryEntries[r]; if (o.tryLoc <= this.prev && n.call(o, "finallyLoc") && this.prev < o.finallyLoc) { var i = o; break; } } i && ("break" === t || "continue" === t) && i.tryLoc <= e && e <= i.finallyLoc && (i = null); var a = i ? i.completion : {}; return a.type = t, a.arg = e, i ? (this.method = "next", this.next = i.finallyLoc, y) : this.complete(a); }, complete: function complete(t, e) { if ("throw" === t.type) throw t.arg; return "break" === t.type || "continue" === t.type ? this.next = t.arg : "return" === t.type ? (this.rval = this.arg = t.arg, this.method = "return", this.next = "end") : "normal" === t.type && e && (this.next = e), y; }, finish: function finish(t) { for (var e = this.tryEntries.length - 1; e >= 0; --e) { var r = this.tryEntries[e]; if (r.finallyLoc === t) return this.complete(r.completion, r.afterLoc), resetTryEntry(r), y; } }, "catch": function _catch(t) { for (var e = this.tryEntries.length - 1; e >= 0; --e) { var r = this.tryEntries[e]; if (r.tryLoc === t) { var n = r.completion; if ("throw" === n.type) { var o = n.arg; resetTryEntry(r); } return o; } } throw Error("illegal catch attempt"); }, delegateYield: function delegateYield(e, r, n) { return this.delegate = { iterator: values(e), resultName: r, nextLoc: n }, "next" === this.method && (this.arg = t), y; } }, e; }
function asyncGeneratorStep(n, t, e, r, o, a, c) { try { var i = n[a](c), u = i.value; } catch (n) { return void e(n); } i.done ? t(u) : Promise.resolve(u).then(r, o); }
function _asyncToGenerator(n) { return function () { var t = this, e = arguments; return new Promise(function (r, o) { var a = n.apply(t, e); function _next(n) { asyncGeneratorStep(a, r, o, _next, _throw, "next", n); } function _throw(n) { asyncGeneratorStep(a, r, o, _next, _throw, "throw", n); } _next(void 0); }); }; }
function _classCallCheck(a, n) { if (!(a instanceof n)) throw new TypeError("Cannot call a class as a function"); }
function _defineProperties(e, r) { for (var t = 0; t < r.length; t++) { var o = r[t]; o.enumerable = o.enumerable || !1, o.configurable = !0, "value" in o && (o.writable = !0), Object.defineProperty(e, _toPropertyKey(o.key), o); } }
function _createClass(e, r, t) { return r && _defineProperties(e.prototype, r), t && _defineProperties(e, t), Object.defineProperty(e, "prototype", { writable: !1 }), e; }
function _toPropertyKey(t) { var i = _toPrimitive(t, "string"); return "symbol" == _typeof(i) ? i : i + ""; }
function _toPrimitive(t, r) { if ("object" != _typeof(t) || !t) return t; var e = t[Symbol.toPrimitive]; if (void 0 !== e) { var i = e.call(t, r || "default"); if ("object" != _typeof(i)) return i; throw new TypeError("@@toPrimitive must return a primitive value."); } return ("string" === r ? String : Number)(t); }


/**
 * 窗口消息处理器基类
 
 */
var WindowHandlerBase = /*#__PURE__*/function () {
  function WindowHandlerBase(loaderPortable) {
    _classCallCheck(this, WindowHandlerBase);
    this.loaderPortable = loaderPortable;
    this.nativeHost = this.loaderPortable.nativeHost;

    // 消息处理器
    this.handlers = {};
    this.extensionWndId = loaderPortable.extensionWndId;
    this.extensionTabId = loaderPortable.extensionTabId; // 暂未使用，预留

    this.__InitWindowHandlerBase();
  }
  return _createClass(WindowHandlerBase, [{
    key: "Init",
    value: function () {
      var _Init = _asyncToGenerator( /*#__PURE__*/_regeneratorRuntime().mark(function _callee() {
        return _regeneratorRuntime().wrap(function _callee$(_context) {
          while (1) switch (_context.prev = _context.next) {
            case 0:
            case "end":
              return _context.stop();
          }
        }, _callee);
      }));
      function Init() {
        return _Init.apply(this, arguments);
      }
      return Init;
    }()
  }, {
    key: "canHandleMessage",
    value: function canHandleMessage(message) {
      if (typeof message.method === 'string') {
        if (this.handlers[message.method] !== undefined) return true;else if (message.method.startsWith("Bridge.")) return true;
      }
      return false;
    }
  }, {
    key: "handleMessage",
    value: function handleMessage(message) {
      if (this.handlers[message.method] !== undefined) this.handlers[message.method](message.params);else {
        // 未处理的Bridge.开头的消息，一般是由于代码不规范导致的，这里记录错误信息
        _Tool_Logger__WEBPACK_IMPORTED_MODULE_0__["default"].Info("[WindowHandlerBase::handleMessage] unhandled msg: ".concat(message.method));
      }
    }
  }, {
    key: "__InitWindowHandlerBase",
    value: function __InitWindowHandlerBase() {
      var _this = this;
      this.handlers['KeepAlive'] = function () {
        _this.nativeHost.Response({
          content: 'KeepAlive'
        });
      };
      this.handlers['Extension.GetVersion'] = function () {
        _this.nativeHost.Response({
          content: window.uiaDispatcher === undefined ? '' : uiaDispatcher.backgroundVersion
        });
      };
      this.handlers['Extension.Init'] = function (params) {
        try {
          var evalService = _this.loaderPortable.evalService;
          // evalService 的生命周期跟随background page
          evalService.Clear();
          evalService.EvalCodeInBackgroundPage(params.code, function () {
            // TODO 对失败的情况进行处理
            _this.nativeHost.Response({
              content: null
            });
          });
        } catch (error) {
          _this.nativeHost.Response({
            error: {
              code: -1,
              message: error.stack
            }
          });
          _Tool_Logger__WEBPACK_IMPORTED_MODULE_0__["default"].Warn('extension init fail', error);
        }
      };
    }
  }, {
    key: "IsAutomationWnd",
    value: function IsAutomationWnd(wnd) {
      if (wnd.id === undefined) return false;
      return (wnd.type === "normal" || wnd.type === "popup") && wnd.id !== this.extensionWndId;
    }

    // @deprecated
  }, {
    key: "WindowCreated",
    value: function WindowCreated(wndId) {
      this.nativeHost.Request('NotifyWindowCreated', wndId);
    }

    // @deprecated
  }, {
    key: "WindowRemoved",
    value: function WindowRemoved(wndId) {
      this.nativeHost.Request('NotifyWindowRemoved', wndId);
    }
  }]);
}();

/***/ }),
/* 14 */
/*!***********************************************************!*\
  !*** ./Src/Handler/WindowHandler_v2/WindowHandler.win.js ***!
  \***********************************************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* harmony import */ var _WindowHandler__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! ../WindowHandler */ 13);
/* harmony import */ var _Tool_Logger__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(/*! ../../Tool/Logger */ 1);
/* harmony import */ var _Tool_BrowserTools__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(/*! ../../Tool/BrowserTools */ 3);
function _typeof(o) { "@babel/helpers - typeof"; return _typeof = "function" == typeof Symbol && "symbol" == typeof Symbol.iterator ? function (o) { return typeof o; } : function (o) { return o && "function" == typeof Symbol && o.constructor === Symbol && o !== Symbol.prototype ? "symbol" : typeof o; }, _typeof(o); }
function _regeneratorRuntime() { "use strict"; /*! regenerator-runtime -- Copyright (c) 2014-present, Facebook, Inc. -- license (MIT): https://github.com/facebook/regenerator/blob/main/LICENSE */ _regeneratorRuntime = function _regeneratorRuntime() { return e; }; var t, e = {}, r = Object.prototype, n = r.hasOwnProperty, o = Object.defineProperty || function (t, e, r) { t[e] = r.value; }, i = "function" == typeof Symbol ? Symbol : {}, a = i.iterator || "@@iterator", c = i.asyncIterator || "@@asyncIterator", u = i.toStringTag || "@@toStringTag"; function define(t, e, r) { return Object.defineProperty(t, e, { value: r, enumerable: !0, configurable: !0, writable: !0 }), t[e]; } try { define({}, ""); } catch (t) { define = function define(t, e, r) { return t[e] = r; }; } function wrap(t, e, r, n) { var i = e && e.prototype instanceof Generator ? e : Generator, a = Object.create(i.prototype), c = new Context(n || []); return o(a, "_invoke", { value: makeInvokeMethod(t, r, c) }), a; } function tryCatch(t, e, r) { try { return { type: "normal", arg: t.call(e, r) }; } catch (t) { return { type: "throw", arg: t }; } } e.wrap = wrap; var h = "suspendedStart", l = "suspendedYield", f = "executing", s = "completed", y = {}; function Generator() {} function GeneratorFunction() {} function GeneratorFunctionPrototype() {} var p = {}; define(p, a, function () { return this; }); var d = Object.getPrototypeOf, v = d && d(d(values([]))); v && v !== r && n.call(v, a) && (p = v); var g = GeneratorFunctionPrototype.prototype = Generator.prototype = Object.create(p); function defineIteratorMethods(t) { ["next", "throw", "return"].forEach(function (e) { define(t, e, function (t) { return this._invoke(e, t); }); }); } function AsyncIterator(t, e) { function invoke(r, o, i, a) { var c = tryCatch(t[r], t, o); if ("throw" !== c.type) { var u = c.arg, h = u.value; return h && "object" == _typeof(h) && n.call(h, "__await") ? e.resolve(h.__await).then(function (t) { invoke("next", t, i, a); }, function (t) { invoke("throw", t, i, a); }) : e.resolve(h).then(function (t) { u.value = t, i(u); }, function (t) { return invoke("throw", t, i, a); }); } a(c.arg); } var r; o(this, "_invoke", { value: function value(t, n) { function callInvokeWithMethodAndArg() { return new e(function (e, r) { invoke(t, n, e, r); }); } return r = r ? r.then(callInvokeWithMethodAndArg, callInvokeWithMethodAndArg) : callInvokeWithMethodAndArg(); } }); } function makeInvokeMethod(e, r, n) { var o = h; return function (i, a) { if (o === f) throw Error("Generator is already running"); if (o === s) { if ("throw" === i) throw a; return { value: t, done: !0 }; } for (n.method = i, n.arg = a;;) { var c = n.delegate; if (c) { var u = maybeInvokeDelegate(c, n); if (u) { if (u === y) continue; return u; } } if ("next" === n.method) n.sent = n._sent = n.arg;else if ("throw" === n.method) { if (o === h) throw o = s, n.arg; n.dispatchException(n.arg); } else "return" === n.method && n.abrupt("return", n.arg); o = f; var p = tryCatch(e, r, n); if ("normal" === p.type) { if (o = n.done ? s : l, p.arg === y) continue; return { value: p.arg, done: n.done }; } "throw" === p.type && (o = s, n.method = "throw", n.arg = p.arg); } }; } function maybeInvokeDelegate(e, r) { var n = r.method, o = e.iterator[n]; if (o === t) return r.delegate = null, "throw" === n && e.iterator["return"] && (r.method = "return", r.arg = t, maybeInvokeDelegate(e, r), "throw" === r.method) || "return" !== n && (r.method = "throw", r.arg = new TypeError("The iterator does not provide a '" + n + "' method")), y; var i = tryCatch(o, e.iterator, r.arg); if ("throw" === i.type) return r.method = "throw", r.arg = i.arg, r.delegate = null, y; var a = i.arg; return a ? a.done ? (r[e.resultName] = a.value, r.next = e.nextLoc, "return" !== r.method && (r.method = "next", r.arg = t), r.delegate = null, y) : a : (r.method = "throw", r.arg = new TypeError("iterator result is not an object"), r.delegate = null, y); } function pushTryEntry(t) { var e = { tryLoc: t[0] }; 1 in t && (e.catchLoc = t[1]), 2 in t && (e.finallyLoc = t[2], e.afterLoc = t[3]), this.tryEntries.push(e); } function resetTryEntry(t) { var e = t.completion || {}; e.type = "normal", delete e.arg, t.completion = e; } function Context(t) { this.tryEntries = [{ tryLoc: "root" }], t.forEach(pushTryEntry, this), this.reset(!0); } function values(e) { if (e || "" === e) { var r = e[a]; if (r) return r.call(e); if ("function" == typeof e.next) return e; if (!isNaN(e.length)) { var o = -1, i = function next() { for (; ++o < e.length;) if (n.call(e, o)) return next.value = e[o], next.done = !1, next; return next.value = t, next.done = !0, next; }; return i.next = i; } } throw new TypeError(_typeof(e) + " is not iterable"); } return GeneratorFunction.prototype = GeneratorFunctionPrototype, o(g, "constructor", { value: GeneratorFunctionPrototype, configurable: !0 }), o(GeneratorFunctionPrototype, "constructor", { value: GeneratorFunction, configurable: !0 }), GeneratorFunction.displayName = define(GeneratorFunctionPrototype, u, "GeneratorFunction"), e.isGeneratorFunction = function (t) { var e = "function" == typeof t && t.constructor; return !!e && (e === GeneratorFunction || "GeneratorFunction" === (e.displayName || e.name)); }, e.mark = function (t) { return Object.setPrototypeOf ? Object.setPrototypeOf(t, GeneratorFunctionPrototype) : (t.__proto__ = GeneratorFunctionPrototype, define(t, u, "GeneratorFunction")), t.prototype = Object.create(g), t; }, e.awrap = function (t) { return { __await: t }; }, defineIteratorMethods(AsyncIterator.prototype), define(AsyncIterator.prototype, c, function () { return this; }), e.AsyncIterator = AsyncIterator, e.async = function (t, r, n, o, i) { void 0 === i && (i = Promise); var a = new AsyncIterator(wrap(t, r, n, o), i); return e.isGeneratorFunction(r) ? a : a.next().then(function (t) { return t.done ? t.value : a.next(); }); }, defineIteratorMethods(g), define(g, u, "Generator"), define(g, a, function () { return this; }), define(g, "toString", function () { return "[object Generator]"; }), e.keys = function (t) { var e = Object(t), r = []; for (var n in e) r.push(n); return r.reverse(), function next() { for (; r.length;) { var t = r.pop(); if (t in e) return next.value = t, next.done = !1, next; } return next.done = !0, next; }; }, e.values = values, Context.prototype = { constructor: Context, reset: function reset(e) { if (this.prev = 0, this.next = 0, this.sent = this._sent = t, this.done = !1, this.delegate = null, this.method = "next", this.arg = t, this.tryEntries.forEach(resetTryEntry), !e) for (var r in this) "t" === r.charAt(0) && n.call(this, r) && !isNaN(+r.slice(1)) && (this[r] = t); }, stop: function stop() { this.done = !0; var t = this.tryEntries[0].completion; if ("throw" === t.type) throw t.arg; return this.rval; }, dispatchException: function dispatchException(e) { if (this.done) throw e; var r = this; function handle(n, o) { return a.type = "throw", a.arg = e, r.next = n, o && (r.method = "next", r.arg = t), !!o; } for (var o = this.tryEntries.length - 1; o >= 0; --o) { var i = this.tryEntries[o], a = i.completion; if ("root" === i.tryLoc) return handle("end"); if (i.tryLoc <= this.prev) { var c = n.call(i, "catchLoc"), u = n.call(i, "finallyLoc"); if (c && u) { if (this.prev < i.catchLoc) return handle(i.catchLoc, !0); if (this.prev < i.finallyLoc) return handle(i.finallyLoc); } else if (c) { if (this.prev < i.catchLoc) return handle(i.catchLoc, !0); } else { if (!u) throw Error("try statement without catch or finally"); if (this.prev < i.finallyLoc) return handle(i.finallyLoc); } } } }, abrupt: function abrupt(t, e) { for (var r = this.tryEntries.length - 1; r >= 0; --r) { var o = this.tryEntries[r]; if (o.tryLoc <= this.prev && n.call(o, "finallyLoc") && this.prev < o.finallyLoc) { var i = o; break; } } i && ("break" === t || "continue" === t) && i.tryLoc <= e && e <= i.finallyLoc && (i = null); var a = i ? i.completion : {}; return a.type = t, a.arg = e, i ? (this.method = "next", this.next = i.finallyLoc, y) : this.complete(a); }, complete: function complete(t, e) { if ("throw" === t.type) throw t.arg; return "break" === t.type || "continue" === t.type ? this.next = t.arg : "return" === t.type ? (this.rval = this.arg = t.arg, this.method = "return", this.next = "end") : "normal" === t.type && e && (this.next = e), y; }, finish: function finish(t) { for (var e = this.tryEntries.length - 1; e >= 0; --e) { var r = this.tryEntries[e]; if (r.finallyLoc === t) return this.complete(r.completion, r.afterLoc), resetTryEntry(r), y; } }, "catch": function _catch(t) { for (var e = this.tryEntries.length - 1; e >= 0; --e) { var r = this.tryEntries[e]; if (r.tryLoc === t) { var n = r.completion; if ("throw" === n.type) { var o = n.arg; resetTryEntry(r); } return o; } } throw Error("illegal catch attempt"); }, delegateYield: function delegateYield(e, r, n) { return this.delegate = { iterator: values(e), resultName: r, nextLoc: n }, "next" === this.method && (this.arg = t), y; } }, e; }
function _createForOfIteratorHelper(r, e) { var t = "undefined" != typeof Symbol && r[Symbol.iterator] || r["@@iterator"]; if (!t) { if (Array.isArray(r) || (t = _unsupportedIterableToArray(r)) || e && r && "number" == typeof r.length) { t && (r = t); var _n = 0, F = function F() {}; return { s: F, n: function n() { return _n >= r.length ? { done: !0 } : { done: !1, value: r[_n++] }; }, e: function e(r) { throw r; }, f: F }; } throw new TypeError("Invalid attempt to iterate non-iterable instance.\nIn order to be iterable, non-array objects must have a [Symbol.iterator]() method."); } var o, a = !0, u = !1; return { s: function s() { t = t.call(r); }, n: function n() { var r = t.next(); return a = r.done, r; }, e: function e(r) { u = !0, o = r; }, f: function f() { try { a || null == t["return"] || t["return"](); } finally { if (u) throw o; } } }; }
function _unsupportedIterableToArray(r, a) { if (r) { if ("string" == typeof r) return _arrayLikeToArray(r, a); var t = {}.toString.call(r).slice(8, -1); return "Object" === t && r.constructor && (t = r.constructor.name), "Map" === t || "Set" === t ? Array.from(r) : "Arguments" === t || /^(?:Ui|I)nt(?:8|16|32)(?:Clamped)?Array$/.test(t) ? _arrayLikeToArray(r, a) : void 0; } }
function _arrayLikeToArray(r, a) { (null == a || a > r.length) && (a = r.length); for (var e = 0, n = Array(a); e < a; e++) n[e] = r[e]; return n; }
function asyncGeneratorStep(n, t, e, r, o, a, c) { try { var i = n[a](c), u = i.value; } catch (n) { return void e(n); } i.done ? t(u) : Promise.resolve(u).then(r, o); }
function _asyncToGenerator(n) { return function () { var t = this, e = arguments; return new Promise(function (r, o) { var a = n.apply(t, e); function _next(n) { asyncGeneratorStep(a, r, o, _next, _throw, "next", n); } function _throw(n) { asyncGeneratorStep(a, r, o, _next, _throw, "throw", n); } _next(void 0); }); }; }
function _classCallCheck(a, n) { if (!(a instanceof n)) throw new TypeError("Cannot call a class as a function"); }
function _defineProperties(e, r) { for (var t = 0; t < r.length; t++) { var o = r[t]; o.enumerable = o.enumerable || !1, o.configurable = !0, "value" in o && (o.writable = !0), Object.defineProperty(e, _toPropertyKey(o.key), o); } }
function _createClass(e, r, t) { return r && _defineProperties(e.prototype, r), t && _defineProperties(e, t), Object.defineProperty(e, "prototype", { writable: !1 }), e; }
function _toPropertyKey(t) { var i = _toPrimitive(t, "string"); return "symbol" == _typeof(i) ? i : i + ""; }
function _toPrimitive(t, r) { if ("object" != _typeof(t) || !t) return t; var e = t[Symbol.toPrimitive]; if (void 0 !== e) { var i = e.call(t, r || "default"); if ("object" != _typeof(i)) return i; throw new TypeError("@@toPrimitive must return a primitive value."); } return ("string" === r ? String : Number)(t); }
function _callSuper(t, o, e) { return o = _getPrototypeOf(o), _possibleConstructorReturn(t, _isNativeReflectConstruct() ? Reflect.construct(o, e || [], _getPrototypeOf(t).constructor) : o.apply(t, e)); }
function _possibleConstructorReturn(t, e) { if (e && ("object" == _typeof(e) || "function" == typeof e)) return e; if (void 0 !== e) throw new TypeError("Derived constructors may only return object or undefined"); return _assertThisInitialized(t); }
function _assertThisInitialized(e) { if (void 0 === e) throw new ReferenceError("this hasn't been initialised - super() hasn't been called"); return e; }
function _isNativeReflectConstruct() { try { var t = !Boolean.prototype.valueOf.call(Reflect.construct(Boolean, [], function () {})); } catch (t) {} return (_isNativeReflectConstruct = function _isNativeReflectConstruct() { return !!t; })(); }
function _getPrototypeOf(t) { return _getPrototypeOf = Object.setPrototypeOf ? Object.getPrototypeOf.bind() : function (t) { return t.__proto__ || Object.getPrototypeOf(t); }, _getPrototypeOf(t); }
function _inherits(t, e) { if ("function" != typeof e && null !== e) throw new TypeError("Super expression must either be null or a function"); t.prototype = Object.create(e && e.prototype, { constructor: { value: t, writable: !0, configurable: !0 } }), Object.defineProperty(t, "prototype", { writable: !1 }), e && _setPrototypeOf(t, e); }
function _setPrototypeOf(t, e) { return _setPrototypeOf = Object.setPrototypeOf ? Object.setPrototypeOf.bind() : function (t, e) { return t.__proto__ = e, t; }, _setPrototypeOf(t, e); }



var WindowHandler = /*#__PURE__*/function (_WindowHandlerBase) {
  function WindowHandler(loaderPortable) {
    _classCallCheck(this, WindowHandler);
    return _callSuper(this, WindowHandler, [loaderPortable]);
  }
  _inherits(WindowHandler, _WindowHandlerBase);
  return _createClass(WindowHandler, [{
    key: "Init",
    value: function () {
      var _Init = _asyncToGenerator( /*#__PURE__*/_regeneratorRuntime().mark(function _callee() {
        var _this = this;
        return _regeneratorRuntime().wrap(function _callee$(_context) {
          while (1) switch (_context.prev = _context.next) {
            case 0:
              return _context.abrupt("return", new Promise(function (resolve) {
                chrome.windows.getAll({
                  populate: true
                }, function (allWnds) {
                  /**
                   * 默认注册所有窗口（不包含devTools，不包含插件窗口)
                   */
                  var wndsToRegister = [];
                  var _iterator = _createForOfIteratorHelper(allWnds),
                    _step;
                  try {
                    for (_iterator.s(); !(_step = _iterator.n()).done;) {
                      var wnd = _step.value;
                      if (_this.IsAutomationWnd(wnd)) {
                        wndsToRegister.push(wnd);
                      }
                    }
                  } catch (err) {
                    _iterator.e(err);
                  } finally {
                    _iterator.f();
                  }
                  _Tool_Logger__WEBPACK_IMPORTED_MODULE_1__["default"].Info('[WindowHandler::Init] wndsToRegister:', wndsToRegister);
                  _Tool_BrowserTools__WEBPACK_IMPORTED_MODULE_2__["default"].ForAllSequential(wndsToRegister, function (wnd, onCompletedCb) {
                    _this.RegisterWindowId(wnd, onCompletedCb);
                  }, function () {
                    _Tool_Logger__WEBPACK_IMPORTED_MODULE_1__["default"].Info('[WindowHandler::Init] register window created event');
                    chrome.windows.onCreated.addListener(function (wnd) {
                      if (_this.IsAutomationWnd(wnd)) {
                        _this.RegisterWindowId(wnd);
                      }
                    });
                    _Tool_Logger__WEBPACK_IMPORTED_MODULE_1__["default"].Info('[WindowHandler::Init] register window removed event');
                    chrome.windows.onRemoved.addListener(function (wnd) {
                      if (wnd2HwndDict[wnd.id]) {
                        delete wnd2HwndDict[wnd.id];
                      }
                    });
                    _Tool_Logger__WEBPACK_IMPORTED_MODULE_1__["default"].Info('[WindowHandler::Init] finish');
                    return resolve();
                  });
                });
              }));
            case 1:
            case "end":
              return _context.stop();
          }
        }, _callee);
      }));
      function Init() {
        return _Init.apply(this, arguments);
      }
      return Init;
    }()
  }, {
    key: "RegisterWindowId",
    value: function RegisterWindowId(wnd) {
      var _this2 = this;
      var finishCallback = arguments.length > 1 && arguments[1] !== undefined ? arguments[1] : null;
      var wndId = wnd.id;
      chrome.windows.update(wndId, {
        focused: true
      }, function (updatedWnd) {
        var _wnd$left, _wnd$top, _wnd$width, _wnd$height;
        if (!updatedWnd) {
          if (chrome.runtime.lastError) {
            _Tool_Logger__WEBPACK_IMPORTED_MODULE_1__["default"].Info("[WindowHandler::RegisterWindowId] Failed to update windowId: ".concat(wndId, " error: ").concat(chrome.runtime.lastError.message));
          }
          _Tool_Logger__WEBPACK_IMPORTED_MODULE_1__["default"].Info("[WindowHandler::RegisterWindowId] ignore register windowid: ".concat(wndId));
          if (finishCallback) finishCallback();
          return;
        }
        _this2.loaderPortable.CallNativeHostFunction('BridgeRegisterWindowId', {
          wndId: wnd.id,
          left: (_wnd$left = wnd.left) !== null && _wnd$left !== void 0 ? _wnd$left : 0,
          top: (_wnd$top = wnd.top) !== null && _wnd$top !== void 0 ? _wnd$top : 0,
          width: (_wnd$width = wnd.width) !== null && _wnd$width !== void 0 ? _wnd$width : 0,
          height: (_wnd$height = wnd.height) !== null && _wnd$height !== void 0 ? _wnd$height : 0
        }, function (params) {
          _Tool_Logger__WEBPACK_IMPORTED_MODULE_1__["default"].Info("[WindowHandler::RegisterWindowId] callback: ".concat(JSON.stringify(params)));
          if (params['hwnd'] != 0) {
            wnd2HwndDict[params['wndId']] = params['hwnd'];
          } else {
            _Tool_Logger__WEBPACK_IMPORTED_MODULE_1__["default"].Info("[WindowHandler::RegisterWindowId] Failed to register windowId: ".concat(wndId, " error: ").concat(params['error']));
          }
          if (finishCallback) finishCallback();
        });
      });
    }
  }]);
}(_WindowHandler__WEBPACK_IMPORTED_MODULE_0__["WindowHandlerBase"]);
/* harmony default export */ __webpack_exports__["default"] = (WindowHandler);

/***/ }),
/* 15 */
/*!***********************************************************!*\
  !*** ./Src/Handler/WindowHandler_v1/WindowHandler.mac.js ***!
  \***********************************************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* harmony import */ var _Tool_Logger__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! ../../Tool/Logger */ 1);
/* harmony import */ var _WindowHandler__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(/*! ../WindowHandler */ 13);
function _typeof(o) { "@babel/helpers - typeof"; return _typeof = "function" == typeof Symbol && "symbol" == typeof Symbol.iterator ? function (o) { return typeof o; } : function (o) { return o && "function" == typeof Symbol && o.constructor === Symbol && o !== Symbol.prototype ? "symbol" : typeof o; }, _typeof(o); }
function _regeneratorRuntime() { "use strict"; /*! regenerator-runtime -- Copyright (c) 2014-present, Facebook, Inc. -- license (MIT): https://github.com/facebook/regenerator/blob/main/LICENSE */ _regeneratorRuntime = function _regeneratorRuntime() { return e; }; var t, e = {}, r = Object.prototype, n = r.hasOwnProperty, o = Object.defineProperty || function (t, e, r) { t[e] = r.value; }, i = "function" == typeof Symbol ? Symbol : {}, a = i.iterator || "@@iterator", c = i.asyncIterator || "@@asyncIterator", u = i.toStringTag || "@@toStringTag"; function define(t, e, r) { return Object.defineProperty(t, e, { value: r, enumerable: !0, configurable: !0, writable: !0 }), t[e]; } try { define({}, ""); } catch (t) { define = function define(t, e, r) { return t[e] = r; }; } function wrap(t, e, r, n) { var i = e && e.prototype instanceof Generator ? e : Generator, a = Object.create(i.prototype), c = new Context(n || []); return o(a, "_invoke", { value: makeInvokeMethod(t, r, c) }), a; } function tryCatch(t, e, r) { try { return { type: "normal", arg: t.call(e, r) }; } catch (t) { return { type: "throw", arg: t }; } } e.wrap = wrap; var h = "suspendedStart", l = "suspendedYield", f = "executing", s = "completed", y = {}; function Generator() {} function GeneratorFunction() {} function GeneratorFunctionPrototype() {} var p = {}; define(p, a, function () { return this; }); var d = Object.getPrototypeOf, v = d && d(d(values([]))); v && v !== r && n.call(v, a) && (p = v); var g = GeneratorFunctionPrototype.prototype = Generator.prototype = Object.create(p); function defineIteratorMethods(t) { ["next", "throw", "return"].forEach(function (e) { define(t, e, function (t) { return this._invoke(e, t); }); }); } function AsyncIterator(t, e) { function invoke(r, o, i, a) { var c = tryCatch(t[r], t, o); if ("throw" !== c.type) { var u = c.arg, h = u.value; return h && "object" == _typeof(h) && n.call(h, "__await") ? e.resolve(h.__await).then(function (t) { invoke("next", t, i, a); }, function (t) { invoke("throw", t, i, a); }) : e.resolve(h).then(function (t) { u.value = t, i(u); }, function (t) { return invoke("throw", t, i, a); }); } a(c.arg); } var r; o(this, "_invoke", { value: function value(t, n) { function callInvokeWithMethodAndArg() { return new e(function (e, r) { invoke(t, n, e, r); }); } return r = r ? r.then(callInvokeWithMethodAndArg, callInvokeWithMethodAndArg) : callInvokeWithMethodAndArg(); } }); } function makeInvokeMethod(e, r, n) { var o = h; return function (i, a) { if (o === f) throw Error("Generator is already running"); if (o === s) { if ("throw" === i) throw a; return { value: t, done: !0 }; } for (n.method = i, n.arg = a;;) { var c = n.delegate; if (c) { var u = maybeInvokeDelegate(c, n); if (u) { if (u === y) continue; return u; } } if ("next" === n.method) n.sent = n._sent = n.arg;else if ("throw" === n.method) { if (o === h) throw o = s, n.arg; n.dispatchException(n.arg); } else "return" === n.method && n.abrupt("return", n.arg); o = f; var p = tryCatch(e, r, n); if ("normal" === p.type) { if (o = n.done ? s : l, p.arg === y) continue; return { value: p.arg, done: n.done }; } "throw" === p.type && (o = s, n.method = "throw", n.arg = p.arg); } }; } function maybeInvokeDelegate(e, r) { var n = r.method, o = e.iterator[n]; if (o === t) return r.delegate = null, "throw" === n && e.iterator["return"] && (r.method = "return", r.arg = t, maybeInvokeDelegate(e, r), "throw" === r.method) || "return" !== n && (r.method = "throw", r.arg = new TypeError("The iterator does not provide a '" + n + "' method")), y; var i = tryCatch(o, e.iterator, r.arg); if ("throw" === i.type) return r.method = "throw", r.arg = i.arg, r.delegate = null, y; var a = i.arg; return a ? a.done ? (r[e.resultName] = a.value, r.next = e.nextLoc, "return" !== r.method && (r.method = "next", r.arg = t), r.delegate = null, y) : a : (r.method = "throw", r.arg = new TypeError("iterator result is not an object"), r.delegate = null, y); } function pushTryEntry(t) { var e = { tryLoc: t[0] }; 1 in t && (e.catchLoc = t[1]), 2 in t && (e.finallyLoc = t[2], e.afterLoc = t[3]), this.tryEntries.push(e); } function resetTryEntry(t) { var e = t.completion || {}; e.type = "normal", delete e.arg, t.completion = e; } function Context(t) { this.tryEntries = [{ tryLoc: "root" }], t.forEach(pushTryEntry, this), this.reset(!0); } function values(e) { if (e || "" === e) { var r = e[a]; if (r) return r.call(e); if ("function" == typeof e.next) return e; if (!isNaN(e.length)) { var o = -1, i = function next() { for (; ++o < e.length;) if (n.call(e, o)) return next.value = e[o], next.done = !1, next; return next.value = t, next.done = !0, next; }; return i.next = i; } } throw new TypeError(_typeof(e) + " is not iterable"); } return GeneratorFunction.prototype = GeneratorFunctionPrototype, o(g, "constructor", { value: GeneratorFunctionPrototype, configurable: !0 }), o(GeneratorFunctionPrototype, "constructor", { value: GeneratorFunction, configurable: !0 }), GeneratorFunction.displayName = define(GeneratorFunctionPrototype, u, "GeneratorFunction"), e.isGeneratorFunction = function (t) { var e = "function" == typeof t && t.constructor; return !!e && (e === GeneratorFunction || "GeneratorFunction" === (e.displayName || e.name)); }, e.mark = function (t) { return Object.setPrototypeOf ? Object.setPrototypeOf(t, GeneratorFunctionPrototype) : (t.__proto__ = GeneratorFunctionPrototype, define(t, u, "GeneratorFunction")), t.prototype = Object.create(g), t; }, e.awrap = function (t) { return { __await: t }; }, defineIteratorMethods(AsyncIterator.prototype), define(AsyncIterator.prototype, c, function () { return this; }), e.AsyncIterator = AsyncIterator, e.async = function (t, r, n, o, i) { void 0 === i && (i = Promise); var a = new AsyncIterator(wrap(t, r, n, o), i); return e.isGeneratorFunction(r) ? a : a.next().then(function (t) { return t.done ? t.value : a.next(); }); }, defineIteratorMethods(g), define(g, u, "Generator"), define(g, a, function () { return this; }), define(g, "toString", function () { return "[object Generator]"; }), e.keys = function (t) { var e = Object(t), r = []; for (var n in e) r.push(n); return r.reverse(), function next() { for (; r.length;) { var t = r.pop(); if (t in e) return next.value = t, next.done = !1, next; } return next.done = !0, next; }; }, e.values = values, Context.prototype = { constructor: Context, reset: function reset(e) { if (this.prev = 0, this.next = 0, this.sent = this._sent = t, this.done = !1, this.delegate = null, this.method = "next", this.arg = t, this.tryEntries.forEach(resetTryEntry), !e) for (var r in this) "t" === r.charAt(0) && n.call(this, r) && !isNaN(+r.slice(1)) && (this[r] = t); }, stop: function stop() { this.done = !0; var t = this.tryEntries[0].completion; if ("throw" === t.type) throw t.arg; return this.rval; }, dispatchException: function dispatchException(e) { if (this.done) throw e; var r = this; function handle(n, o) { return a.type = "throw", a.arg = e, r.next = n, o && (r.method = "next", r.arg = t), !!o; } for (var o = this.tryEntries.length - 1; o >= 0; --o) { var i = this.tryEntries[o], a = i.completion; if ("root" === i.tryLoc) return handle("end"); if (i.tryLoc <= this.prev) { var c = n.call(i, "catchLoc"), u = n.call(i, "finallyLoc"); if (c && u) { if (this.prev < i.catchLoc) return handle(i.catchLoc, !0); if (this.prev < i.finallyLoc) return handle(i.finallyLoc); } else if (c) { if (this.prev < i.catchLoc) return handle(i.catchLoc, !0); } else { if (!u) throw Error("try statement without catch or finally"); if (this.prev < i.finallyLoc) return handle(i.finallyLoc); } } } }, abrupt: function abrupt(t, e) { for (var r = this.tryEntries.length - 1; r >= 0; --r) { var o = this.tryEntries[r]; if (o.tryLoc <= this.prev && n.call(o, "finallyLoc") && this.prev < o.finallyLoc) { var i = o; break; } } i && ("break" === t || "continue" === t) && i.tryLoc <= e && e <= i.finallyLoc && (i = null); var a = i ? i.completion : {}; return a.type = t, a.arg = e, i ? (this.method = "next", this.next = i.finallyLoc, y) : this.complete(a); }, complete: function complete(t, e) { if ("throw" === t.type) throw t.arg; return "break" === t.type || "continue" === t.type ? this.next = t.arg : "return" === t.type ? (this.rval = this.arg = t.arg, this.method = "return", this.next = "end") : "normal" === t.type && e && (this.next = e), y; }, finish: function finish(t) { for (var e = this.tryEntries.length - 1; e >= 0; --e) { var r = this.tryEntries[e]; if (r.finallyLoc === t) return this.complete(r.completion, r.afterLoc), resetTryEntry(r), y; } }, "catch": function _catch(t) { for (var e = this.tryEntries.length - 1; e >= 0; --e) { var r = this.tryEntries[e]; if (r.tryLoc === t) { var n = r.completion; if ("throw" === n.type) { var o = n.arg; resetTryEntry(r); } return o; } } throw Error("illegal catch attempt"); }, delegateYield: function delegateYield(e, r, n) { return this.delegate = { iterator: values(e), resultName: r, nextLoc: n }, "next" === this.method && (this.arg = t), y; } }, e; }
function _createForOfIteratorHelper(r, e) { var t = "undefined" != typeof Symbol && r[Symbol.iterator] || r["@@iterator"]; if (!t) { if (Array.isArray(r) || (t = _unsupportedIterableToArray(r)) || e && r && "number" == typeof r.length) { t && (r = t); var _n = 0, F = function F() {}; return { s: F, n: function n() { return _n >= r.length ? { done: !0 } : { done: !1, value: r[_n++] }; }, e: function e(r) { throw r; }, f: F }; } throw new TypeError("Invalid attempt to iterate non-iterable instance.\nIn order to be iterable, non-array objects must have a [Symbol.iterator]() method."); } var o, a = !0, u = !1; return { s: function s() { t = t.call(r); }, n: function n() { var r = t.next(); return a = r.done, r; }, e: function e(r) { u = !0, o = r; }, f: function f() { try { a || null == t["return"] || t["return"](); } finally { if (u) throw o; } } }; }
function _unsupportedIterableToArray(r, a) { if (r) { if ("string" == typeof r) return _arrayLikeToArray(r, a); var t = {}.toString.call(r).slice(8, -1); return "Object" === t && r.constructor && (t = r.constructor.name), "Map" === t || "Set" === t ? Array.from(r) : "Arguments" === t || /^(?:Ui|I)nt(?:8|16|32)(?:Clamped)?Array$/.test(t) ? _arrayLikeToArray(r, a) : void 0; } }
function _arrayLikeToArray(r, a) { (null == a || a > r.length) && (a = r.length); for (var e = 0, n = Array(a); e < a; e++) n[e] = r[e]; return n; }
function asyncGeneratorStep(n, t, e, r, o, a, c) { try { var i = n[a](c), u = i.value; } catch (n) { return void e(n); } i.done ? t(u) : Promise.resolve(u).then(r, o); }
function _asyncToGenerator(n) { return function () { var t = this, e = arguments; return new Promise(function (r, o) { var a = n.apply(t, e); function _next(n) { asyncGeneratorStep(a, r, o, _next, _throw, "next", n); } function _throw(n) { asyncGeneratorStep(a, r, o, _next, _throw, "throw", n); } _next(void 0); }); }; }
function _classCallCheck(a, n) { if (!(a instanceof n)) throw new TypeError("Cannot call a class as a function"); }
function _defineProperties(e, r) { for (var t = 0; t < r.length; t++) { var o = r[t]; o.enumerable = o.enumerable || !1, o.configurable = !0, "value" in o && (o.writable = !0), Object.defineProperty(e, _toPropertyKey(o.key), o); } }
function _createClass(e, r, t) { return r && _defineProperties(e.prototype, r), t && _defineProperties(e, t), Object.defineProperty(e, "prototype", { writable: !1 }), e; }
function _toPropertyKey(t) { var i = _toPrimitive(t, "string"); return "symbol" == _typeof(i) ? i : i + ""; }
function _toPrimitive(t, r) { if ("object" != _typeof(t) || !t) return t; var e = t[Symbol.toPrimitive]; if (void 0 !== e) { var i = e.call(t, r || "default"); if ("object" != _typeof(i)) return i; throw new TypeError("@@toPrimitive must return a primitive value."); } return ("string" === r ? String : Number)(t); }
function _callSuper(t, o, e) { return o = _getPrototypeOf(o), _possibleConstructorReturn(t, _isNativeReflectConstruct() ? Reflect.construct(o, e || [], _getPrototypeOf(t).constructor) : o.apply(t, e)); }
function _possibleConstructorReturn(t, e) { if (e && ("object" == _typeof(e) || "function" == typeof e)) return e; if (void 0 !== e) throw new TypeError("Derived constructors may only return object or undefined"); return _assertThisInitialized(t); }
function _assertThisInitialized(e) { if (void 0 === e) throw new ReferenceError("this hasn't been initialised - super() hasn't been called"); return e; }
function _isNativeReflectConstruct() { try { var t = !Boolean.prototype.valueOf.call(Reflect.construct(Boolean, [], function () {})); } catch (t) {} return (_isNativeReflectConstruct = function _isNativeReflectConstruct() { return !!t; })(); }
function _getPrototypeOf(t) { return _getPrototypeOf = Object.setPrototypeOf ? Object.getPrototypeOf.bind() : function (t) { return t.__proto__ || Object.getPrototypeOf(t); }, _getPrototypeOf(t); }
function _inherits(t, e) { if ("function" != typeof e && null !== e) throw new TypeError("Super expression must either be null or a function"); t.prototype = Object.create(e && e.prototype, { constructor: { value: t, writable: !0, configurable: !0 } }), Object.defineProperty(t, "prototype", { writable: !1 }), e && _setPrototypeOf(t, e); }
function _setPrototypeOf(t, e) { return _setPrototypeOf = Object.setPrototypeOf ? Object.setPrototypeOf.bind() : function (t, e) { return t.__proto__ = e, t; }, _setPrototypeOf(t, e); }


var WindowHandler = /*#__PURE__*/function (_WindowHandlerBase) {
  function WindowHandler(loaderPortable) {
    var _this;
    _classCallCheck(this, WindowHandler);
    _this = _callSuper(this, WindowHandler, [loaderPortable]);
    _this.__InitWindowHandler();
    return _this;
  }
  _inherits(WindowHandler, _WindowHandlerBase);
  return _createClass(WindowHandler, [{
    key: "__InitWindowHandler",
    value: function __InitWindowHandler() {
      var _this2 = this;
      this.handlers['Window.SetHwnd'] = function (params) {
        _Tool_Logger__WEBPACK_IMPORTED_MODULE_0__["default"].Info("Window.SetHwnd: ".concat(JSON.stringify(params)));
        wnd2HwndDict[params['wndId']] = params['hwnd'];
      };
      this.handlers['Bridge.AdjustConflictWnds'] = function (params) {
        var left = params['left'];
        var top = params['top'];
        var width = params['width'];
        var height = params['height'];
        var hwnds = params['hwnds'];
        chrome.windows.getAll(function (wnds) {
          var foundWndIds = wnds.filter(function (wnd) {
            return wnd.left === left && wnd.top === top && wnd.width === width && wnd.height === height && _this2.IsAutomationWnd(wnd);
          }).map(function (wnd) {
            return wnd.id;
          });
          if (hwnds.length === foundWndIds.length) {
            hwnds.sort();
            foundWndIds.sort();
            for (var i = 0; i < hwnds.length; i++) {
              wnd2HwndDict[foundWndIds[i]] = hwnds[i];
            }
            _Tool_Logger__WEBPACK_IMPORTED_MODULE_0__["default"].Info("AdjustConflictWnds ".concat(foundWndIds, " ").concat(hwnds));
          } else {
            _Tool_Logger__WEBPACK_IMPORTED_MODULE_0__["default"].Info('AdjustConflictWnds failed, length not match');
          }
        });
      };
    }
  }, {
    key: "Init",
    value: function () {
      var _Init = _asyncToGenerator( /*#__PURE__*/_regeneratorRuntime().mark(function _callee() {
        var _this3 = this;
        return _regeneratorRuntime().wrap(function _callee$(_context) {
          while (1) switch (_context.prev = _context.next) {
            case 0:
              return _context.abrupt("return", new Promise(function (resolve) {
                chrome.windows.getAll({
                  populate: true
                }, function (wnds) {
                  chrome.windows.onCreated.addListener(function (wnd) {
                    if (_this3.IsAutomationWnd(wnd)) {
                      _this3.WindowCreated(wnd.id);
                      setTimeout(function () {
                        // bridge can't get accurate window coordinate when window is created
                        _this3.WindowAdjust(wnd);
                      }, 1000);
                    }
                  });
                  chrome.windows.onRemoved.addListener(function (wndId) {
                    _this3.WindowRemoved(wndId);
                    delete wnd2HwndDict[wndId];
                  });
                  var wndsCount = 0;
                  var lastWndId = 0;
                  var _iterator = _createForOfIteratorHelper(wnds),
                    _step;
                  try {
                    for (_iterator.s(); !(_step = _iterator.n()).done;) {
                      var wnd = _step.value;
                      if (_this3.IsAutomationWnd(wnd)) {
                        if (++wndsCount === 2) break;
                        lastWndId = wnd.id;
                      }
                    }
                  } catch (err) {
                    _iterator.e(err);
                  } finally {
                    _iterator.f();
                  }
                  if (wndsCount === 1) {
                    _this3.WindowCreated(lastWndId);
                  } else {
                    var wndIds = wnds.filter(function (wnd) {
                      return _this3.IsAutomationWnd(wnd);
                    }).map(function (wnd) {
                      return wnd.id;
                    });
                    _Tool_Logger__WEBPACK_IMPORTED_MODULE_0__["default"].Info("[WindowHandler::Init] detect multi automation windows:", wndIds);
                  }
                  var _iterator2 = _createForOfIteratorHelper(wnds),
                    _step2;
                  try {
                    for (_iterator2.s(); !(_step2 = _iterator2.n()).done;) {
                      var _wnd = _step2.value;
                      _this3.WindowAdjust(_wnd);
                    }
                  } catch (err) {
                    _iterator2.e(err);
                  } finally {
                    _iterator2.f();
                  }
                  return resolve();
                });
              }));
            case 1:
            case "end":
              return _context.stop();
          }
        }, _callee);
      }));
      function Init() {
        return _Init.apply(this, arguments);
      }
      return Init;
    }()
  }, {
    key: "WindowAdjust",
    value: function WindowAdjust(wnd) {
      var _wnd$left, _wnd$top, _wnd$width, _wnd$height;
      if (!this.IsAutomationWnd(wnd)) return;
      var wndId = wnd.id;
      var left = (_wnd$left = wnd.left) !== null && _wnd$left !== void 0 ? _wnd$left : 0;
      var top = (_wnd$top = wnd.top) !== null && _wnd$top !== void 0 ? _wnd$top : 0;
      var width = (_wnd$width = wnd.width) !== null && _wnd$width !== void 0 ? _wnd$width : 0;
      var height = (_wnd$height = wnd.height) !== null && _wnd$height !== void 0 ? _wnd$height : 0;
      var request = {
        wndId: wndId,
        left: left,
        top: top,
        width: width,
        height: height
      };
      _Tool_Logger__WEBPACK_IMPORTED_MODULE_0__["default"].Debug("NotifyWindowAdjust request: ".concat(JSON.stringify(request)));
      this.nativeHost.Request('NotifyWindowAdjust', request);
    }
  }]);
}(_WindowHandler__WEBPACK_IMPORTED_MODULE_1__["WindowHandlerBase"]);
/* harmony default export */ __webpack_exports__["default"] = (WindowHandler);

/***/ }),
/* 16 */
/*!*****************************!*\
  !*** ./Src/Tool/Version.js ***!
  \*****************************/
/*! exports provided: CompareVersion */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "CompareVersion", function() { return CompareVersion; });
var CompareVersion = function CompareVersion(version1, version2) {
  var v1 = version1.split('.');
  var v2 = version2.split('.');
  for (var i = 0; i < v1.length; i++) {
    if (parseInt(v1[i]) > parseInt(v2[i])) {
      return 1;
    } else if (parseInt(v1[i]) < parseInt(v2[i])) {
      return -1;
    }
  }
  return 0;
};

/***/ }),
/* 17 */,
/* 18 */
/*!**********************************!*\
  !*** ./Src/Background.Static.js ***!
  \**********************************/
/*! no exports provided */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* harmony import */ var _LoaderPortable__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! ./LoaderPortable */ 5);

var loaderPortable = new _LoaderPortable__WEBPACK_IMPORTED_MODULE_0__["default"](false);
loaderPortable.Init();

/***/ })
/******/ ]);