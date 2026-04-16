#ifndef FX_FXMATRIX_H_
#define FX_FXMATRIX_H_
#include "FXMath.h"

FX_VOID			FX_VectNorm(Vect3 a);
FX_VOID			FX_Vect3AToB(Vect3 A, Vect3 B);
FX_VOID			FX_VectCross(Vect3 a, Vect3 b, Vect3 result);
FX_VOID			FX_VectAdd(Vect3 a, Vect3 b, Vect3 result);
FX_VOID			FX_VectAddToA(Vect3 a, Vect3 b);
FX_BOOL			FX_Matrix2ZYZ(Matrix3 m, Vect3  ret);
FX_BOOL			FX_Matrix2ZYX(Matrix3 m, Vect3  ret);
FX_VOID			FX_MatRotAxis(Vect3 rot_dir, FX_DOUBLE rot_angle, Matrix3 m, Matrix3 m_roted);
FX_VOID			FX_MMV3(Matrix3 L, Vect3 R, Vect3 Result);
FX_VOID			FX_MMM33(Matrix3 L, Matrix3 R, Matrix3 Result);
FX_VOID			FX_M33Copy(Matrix3 src, Matrix3 dst);
FX_VOID			FX_M33Trans( Matrix3 Org, Matrix3 Result);
FX_VOID			Tmat(FX_DOUBLE DH[4], Matrix4 T);
FX_VOID			FX_IdentM44(Matrix4 m);
FX_VOID			FX_IdentM33(Matrix3 m);
FX_VOID			FX_M44Copy(Matrix4 src, Matrix4 dst);

FX_VOID			FX_PGPointMap(Matrix4 a_to_b, Vect3 in_a, Vect3 ret_in_b);
FX_VOID			FX_PGVectMap(Matrix4 a_to_b, Vect3 in_a, Vect3 ret_in_b);
FX_VOID			FX_PGVectMapInv(Matrix4 a_to_b, Vect3 ret_in_a, Vect3 in_b);
FX_VOID			FX_PGMatrixInv(Matrix4 pg, Matrix4 pginv);
FX_VOID			FX_MMM44(Matrix4 L, Matrix4 R, Matrix4 Result);
FX_VOID			FX_PGMult(Matrix4 L, Matrix4 R, Matrix4 Result);

FX_VOID			FX_PGGetGes(PosGes src, Matrix3 ges);
FX_VOID			FX_PGGetPos(PosGes src, Vect3 pos);
FX_VOID			FX_PGGetAxisX(PosGes src, Vect3 axis_x);
FX_VOID			FX_PGGetAxisY(PosGes src, Vect3 axis_y);
FX_VOID			FX_PGGetAxisZ(PosGes src, Vect3 axis_z);


#endif
