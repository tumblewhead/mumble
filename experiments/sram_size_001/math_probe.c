#include "tiny_math.h"
double evaluate(unsigned op,double x,double y){
 switch(op){case 0:return exp(x);case 1:return log(x);case 2:return sqrt(x);case 3:return hypot(x,y);case 4:return tanh(x);case 5:return atanh(x);default:return NAN;}
}
